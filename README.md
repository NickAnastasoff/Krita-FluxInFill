# Krita-FluxInFill

**Flux Inpaint** — Infilling transparent areas in Krita using Replicate's API.

---

## ✨ Overview

**Krita-FluxInFill** is a plugin for Krita that allows you to automatically **inpaint (fill in)** transparent pixels in your artwork using AI. It works via Replicate’s API, specifically using the `black-forest-labs/flux-fill-pro` model, and seamlessly integrates into Krita’s UI with a handy dockable panel.

---

## 🛠 Features

- Fill transparent areas with AI-generated content based on your prompt
- Supports batch processing across multiple layers
- Adjustable thread settings for faster batch jobs
- Simple and advanced modes
- Debugging mode to keep temporary files
- Clean new layers without modifying your originals

---

## 📥 Installation

1. Download or clone this repository.
2. Copy the plugin files into Krita’s `pykrita` plugins directory.
   - Typically found at:
     - Windows: `C:\Users\<YourName>\AppData\Roaming\krita\pykrita\`
     - Linux: `~/.local/share/krita/pykrita/`
     - MacOS: `~/Library/Application Support/Krita/pykrita/`
3. Restart Krita.
4. Go to `Settings > Dockers` and enable **Flux Inpaint**.

---

## 🚀 Usage

1. **Set up your Replicate API key**:
   - Create an account at [Replicate](https://replicate.com/).
   - Get your API token and paste it into the plugin’s API Token field.

2. **Prepare your canvas**:
   - Erase or make transparent the parts you want to inpaint.

3. **Describe your fill**:
   - Enter a prompt describing what should appear in the erased areas.

4. **Run the Inpaint**:
   - Press **Inpaint** — the plugin will create a new filled-in layer!

---

## ⚙️ Advanced Options

- **Batch Mode**: Process multiple selected layers at once.
- **Custom Threads**: Fine-tune thread usage for large batch jobs.
- **Debug Mode**: Keep temporary files for troubleshooting or inspection.

---

## 📝 Notes

- The plugin creates a **new layer** for the inpainted result and hides the original layer, preserving your work.
- Temporary files are automatically cleaned unless Debug mode is active.
- If there are issues during processing (API errors, network failures), logs are displayed inside the panel.
