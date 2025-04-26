import base64
import json
import multiprocessing
import os
import ssl
import tempfile
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtGui import QImage, qAlpha, QColor


from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtCore import QRectF
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from krita import DockWidgetFactory, DockWidgetFactoryBase, Extension, InfoObject, Krita

REPLICATE_ENDPOINT = (
    "https://api.replicate.com/v1/models/black-forest-labs/flux-fill-pro/predictions"
)
SSL_CTX = ssl._create_unverified_context()
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=SSL_CTX))
urllib.request.install_opener(opener)


# helpers
def encode_b64(path: str) -> str:
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


# dock widget
class FluxFillDock(QDockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flux Inpaint")
        root = QWidget()
        lay = QVBoxLayout(root)
        # API token
        row = QHBoxLayout()
        row.addWidget(QLabel("API Token:"))
        self.api = QLineEdit()
        self.api.setEchoMode(QLineEdit.Password)
        self.api.textChanged.connect(self._save_token)
        row.addWidget(self.api)
        lay.addLayout(row)
        # Prompt
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Prompt:"))
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Describe what should appear …")
        prow.addWidget(self.prompt)
        lay.addLayout(prow)
        # Batch / advanced
        top = QHBoxLayout()
        self.batch = QCheckBox("Batch (selected layers)")
        self.batch.stateChanged.connect(self._sync_thr)
        self.adv = QCheckBox("Advanced")
        self.adv.stateChanged.connect(self._toggle_adv)
        top.addWidget(self.batch)
        top.addWidget(self.adv)
        lay.addLayout(top)
        # Advanced box
        self.adv_box = QGroupBox("Advanced Options")
        self.adv_box.setVisible(False)
        ab = QVBoxLayout(self.adv_box)
        thr = QHBoxLayout()
        self.auto_thr = QCheckBox("Threads (AUTO)")
        self.auto_thr.setChecked(True)
        self.auto_thr.stateChanged.connect(self._sync_thr)
        self.thr_spin = QSpinBox()
        self.thr_spin.setMinimum(1)
        self.thr_spin.setValue(os.cpu_count() or 4)
        thr.addWidget(self.auto_thr)
        thr.addWidget(self.thr_spin)
        ab.addLayout(thr)
        self.debug = QCheckBox("Debug (keep temp + verbose)")
        ab.addWidget(self.debug)
        lay.addWidget(self.adv_box)
        # Buttons
        btn = QHBoxLayout()
        run = QPushButton("Inpaint")
        run.clicked.connect(self._run)
        copy = QPushButton("Copy Log")
        copy.clicked.connect(
            lambda: (
                QApplication.clipboard().setText(self.log.toPlainText()),
                QMessageBox.information(self, "Copied", "Log copied."),
            )
        )
        btn.addWidget(run)
        btn.addWidget(copy)
        lay.addLayout(btn)
        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(40)
        lay.addWidget(self.log)
        self.setWidget(root)
        self._load_token()

    # settings helpers
    def _save_token(self):
        Krita.instance().writeSetting("FLUX_FILL", "api_token", self.api.text())

    def _load_token(self):
        self.api.setText(Krita.instance().readSetting("FLUX_FILL", "api_token", ""))

    # UI helpers
    def _toggle_adv(self):
        self.adv_box.setVisible(self.adv.isChecked())
        self._sync_thr()

    def _sync_thr(self):
        v = self.adv.isChecked() and self.batch.isChecked()
        self.auto_thr.setVisible(v)
        self.thr_spin.setVisible(v and not self.auto_thr.isChecked())

    # main action
    def _run(self):
        token = self.api.text().strip()
        prompt = self.prompt.text().strip()
        if not token:
            self.log.setText("Error: API token blank.")
            return
        if not prompt:
            self.log.setText("Error: Prompt blank.")
            return
        app = Krita.instance()
        doc = app.activeDocument()
        win = app.activeWindow()
        view = win.activeView() if win else None
        if not (doc and view):
            self.log.setText("No active document/view.")
            return
        nodes = view.selectedNodes() if self.batch.isChecked() else [doc.activeNode()]
        if not nodes:
            self.log.setText("No layer selected.")
            return
        dlg = QProgressDialog("Inpainting…", "Cancel", 0, 100, win.qwindow())
        dlg.setWindowModality(Qt.WindowModal)
        dlg.show()
        workers = (
            self.thr_spin.value()
            if (self.adv.isChecked() and not self.auto_thr.isChecked())
            else (os.cpu_count() or 4)
        )
        doc.setBatchmode(True)
        dlg.setValue(5)
        proc = succ = 0
        errors = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            tasks = [pool.submit(self._process, n, prompt, token, doc) for n in nodes]
            for t in as_completed(tasks):
                proc += 1
                try:
                    res = t.result()
                    succ += res.startswith("Success")
                except Exception as e:
                    res = f"Exception: {e}"
                    errors.append(str(e))
                self.log.append(f"{proc}/{len(nodes)} → {res}")
                dlg.setValue(5 + int(90 * proc / len(nodes)))
                QApplication.processEvents()
        doc.setBatchmode(False)
        dlg.setValue(100)
        dlg.close()
        self.log.append(f"\nCompleted. {succ}/{len(nodes)} succeeded.")
        if errors:
            self.log.append("Errors: " + "; ".join(errors))

    # per‑layer
    def _process(self, node, prompt, token, doc):
        tdir = tempfile.gettempdir()
        ident = threading.get_ident()
        img = os.path.join(tdir, f"flux_img_{ident}.png")
        mask = os.path.join(tdir, f"flux_mask_{ident}.png")
        if not self._export(node, doc, img):
            return "Error: export failed"
        self._mask(img, mask)
        payload = {
            "input": {
                "image": encode_b64(img),
                "mask": encode_b64(mask),
                "prompt": prompt,
            }
        }
        req = urllib.request.Request(
            REPLICATE_ENDPOINT,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180, context=SSL_CTX) as r:
                if r.status not in (200, 201):
                    return f"HTTP {r.status}"
                data = json.loads(r.read().decode())
        except Exception as e:
            return f"Request error: {e}"
        finally:
            if not self.debug.isChecked():
                for p in (img, mask):
                    if os.path.exists(p):
                        os.remove(p)
        out = data.get("output")
        out = out[0] if isinstance(out, list) else out
        if not out:
            return "Error: no output URL"
        out_p = os.path.join(tdir, f"flux_out_{ident}.png")
        if not self._fetch_png(out, out_p):
            return "Download failed"

        q = QImage(out_p)
        layer = doc.createNode(f"{node.name()} FLUX", "paintlayer")
        layer.setPixelData(
            q.constBits().asstring(q.byteCount()), 0, 0, q.width(), q.height()
        )
        doc.rootNode().addChildNode(layer, node)
        node.setVisible(False)
        doc.refreshProjection()
        if not self.debug.isChecked() and os.path.exists(out_p):
            os.remove(out_p)
        return f"Success: {node.name()} inpainted"

    # export
    def _export(self, node, doc, path):
        info = InfoObject()
        info.setProperty("alpha", True)  # keep transparency
        info.setProperty("flatten", True)  # one composite pass

        # 1) full-canvas PNG straight from the document
        if doc.exportImage(path, info): 
            return True

        # 2) manual projection copy
        w, h = doc.width(), doc.height()
        raw = doc.projectionPixelData(0, 0, w, h)
        ok = QImage(raw, w, h, QImage.Format_ARGB32).save(path)
        return ok

    def _mask(self, src, dst):
        """binary mask from alpha channel"""

        img = QImage(src).convertToFormat(QImage.Format_ARGB32)

        w, h = img.width(), img.height()
        mask = QImage(w, h, QImage.Format_RGB32)

        white = QColor(255, 255, 255).rgb()
        black = QColor(0, 0, 0).rgb()

        for y in range(h):
            for x in range(w):
                a = qAlpha(img.pixel(x, y))
                mask.setPixel(x, y, white if a == 0 else black)

        mask.save(dst, "PNG")

    def _fetch_png(self, url, path):
        try:
            with urllib.request.urlopen(url, context=SSL_CTX, timeout=180) as r, open(
                path, "wb"
            ) as f:
                f.write(r.read())
            return True
        except Exception as e:
            self.log.append(f"PNG download error: {e}")
            return False


# extension glue
class FluxFillExt(Extension):
    def __init__(self, p):
        super().__init__(p)

    def setup(self):
        pass

    def createActions(self, w):
        pass


Krita.instance().addExtension(FluxFillExt(Krita.instance()))
Application.addDockWidgetFactory(
    DockWidgetFactory(
        "flux_fill_dock", DockWidgetFactoryBase.DockRight, lambda: FluxFillDock()
    )
)
