# Third-party components

The Windows package contains these third-party components:

- **PySide6 / Qt** — Qt for Python and Qt Multimedia, used under LGPLv3. License texts are included in `LICENSES/Qt-LGPLv3.txt` and `LICENSES/GPLv3.txt`. Source and licensing information: https://doc.qt.io/qtforpython-6/ and https://www.qt.io/licensing/.
- **imageio-ffmpeg 0.6.0** — BSD-2-Clause Python wrapper. License text is included in `LICENSES/Imageio-FFmpeg-BSD-2-Clause.txt`. Source: https://github.com/imageio/imageio-ffmpeg.
- **FFmpeg 7.1** — bundled by the platform-specific imageio-ffmpeg wheel and used as a separate process to decode WMA audio. GPL v2 license text is included in `LICENSES/FFmpeg-GPLv2.txt`. The GitHub release includes `FFmpeg-source-7.1.tar.xz`. FFmpeg source and build information: https://ffmpeg.org/ and https://github.com/FFmpeg/FFmpeg/tree/n7.1. Run the packaged FFmpeg executable with `-buildconf` to inspect its enabled components.

The player does not use JetAudio code, artwork, or trademarks.
