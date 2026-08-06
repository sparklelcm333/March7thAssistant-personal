<div align="center">
  <h1 align="center">
    <img src="./assets/screenshot/March7th.png" width="200">
    <br/>
    March7thAssistant-personal
  </h1>
</div>

<br/>

<div align="center">
🌟 Click the Star in the upper-right corner to get update notifications for this project on GitHub.
</div>

<div align="center">
    <img src="assets/screenshot/star.gif" alt="Star" width="186" height="60">
</div>

<br/>

<div align="center">

[简体中文](./README.md) | [繁體中文](./README_TW.md) | **English** | [日本語](./README_JA.md) | [한국어](./README_KR.md)

**This document was translated from the Simplified Chinese version using AI. Last updated: 2026-04-24. If anything differs, the Simplified Chinese version takes precedence.**

**The in-game language currently supports Simplified Chinese only.**

Quick start: [Tutorial](https://m7a.top/#/assets/docs/Tutorial_en)

Before asking for help, please check: [FAQ](https://m7a.top/#/assets/docs/FAQ_en)

</div>

## Feature Overview

- **Daily**: Spend Trailblaze Power, Daily Training, claim rewards, dispatch, field farming
- **Weekly**: Echo of War, Currency Wars, Divergent Universe, Memory of Chaos, Pure Fiction, Apocalyptic Shadow
- **Cloud Honkai: Star Rail**: Supports background execution, headless execution, and Docker deployment
- **Gacha record export**: Supports the [UIGF](https://uigf.org/zh/standards/uigf.html) / [SRGF](https://uigf.org/zh/standards/srgf.html) standards
- **Toolbox**: Auto dialogue, FPS unlock, redemption codes
- Task results such as Daily Training support **push notifications**
- Supports **automatic start** after task refresh or when Trailblaze Power recovers to a specified value
- Supports **sound alerts, automatic game exit, shutdown, and more** after tasks finish


## Interface Preview

![README](assets/screenshot/README.png)

## Notes

- This is a personal customized version, stability is not guaranteed. For the original (upstream) experience, visit [moesnow/March7thAssistant](https://github.com/moesnow/March7thAssistant)
- Pull requests are welcome. Please read the [contribution guide](CONTRIBUTING.md) before submitting.

## Download and Installation

Download the latest release from [Releases](https://github.com/sparklelcm333/March7thAssistant-personal/releases/latest), extract it, and double-click `March7thAssistant.exe` with the March 7th icon to open the GUI.

## Running from Source

If you are completely new to this, use the packaged release above. You can ignore the rest of this section.

Python 3.12 or newer is recommended.

On Windows, if you launch from a terminal, it is recommended to open PowerShell, Windows Terminal, or CMD as Administrator. On Windows 11 24H2 or later, you can also use [Sudo for Windows](https://learn.microsoft.com/zh-cn/windows/advanced-settings/sudo/).

```cmd
# Installation (using venv is recommended)
git clone https://github.com/sparklelcm333/March7thAssistant-personal
cd March7thAssistant-personal
pip install -r requirements.txt
python main.py

# Update
git pull
```

If you use `uv`, it is recommended to use the built-in `pyproject.toml` workflow directly:

```cmd
# Installation (using uv)
git clone https://github.com/sparklelcm333/March7thAssistant-personal
cd March7thAssistant-personal
uv sync

# Launch the GUI
uv run python main.py

# Show CLI help
uv run python main.py -h

# Run the full workflow
uv run python main.py

# Run Daily Training
uv run python main.py daily
```

<details>
<summary>Development Notes</summary>

To obtain the crop coordinates used by crop parameters, you can use the capture screenshot feature in the toolbox.

</details>

---

If you like this project, you can support the author with a coffee via WeChat ☕

Your support helps keep the project developed and maintained.

![sponsor](assets/app/images/sponsor.jpg)

---

## Related Projects

March7thAssistant depends on the following open-source projects and runtime dependencies. Thanks to all maintainers and contributors.

- Simulated Universe automation [https://github.com/CHNZYX/Auto_Simulated_Universe](https://github.com/CHNZYX/Auto_Simulated_Universe): provides Simulated Universe related capabilities
- Field farming automation [https://github.com/linruowuyin/Fhoe-Rail](https://github.com/linruowuyin/Fhoe-Rail): provides field farming related capabilities
- OCR text recognition [https://github.com/RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR): provides in-game text recognition
- GUI component library [https://github.com/zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets): provides the main interface components and interaction experience
- Image processing and automation related dependencies `OpenCV`, `PyAutoGUI`, and others: provide screenshot capture, image processing, and foundational automation capabilities
- Inference acceleration related dependencies `ONNX Runtime`, `OpenVINO`: provide CPU / GPU acceleration for OCR and model inference

Additionally, `requirements.txt` contains many lower-level dependencies that are not listed one by one here. Thanks as well to those projects for supporting this project.

