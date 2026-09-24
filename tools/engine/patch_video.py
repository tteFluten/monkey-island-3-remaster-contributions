"""Use the existing MP4 path with native timing, subtitles and safe fallback."""
from pathlib import Path


def patch(root, edit):
    player = 'engines/scumm/hd_video_player.cpp'
    edit(player, '// POSIX headers for popen/pclose/fread',
         '#define FORBIDDEN_SYMBOL_ALLOW_ALL\n// POSIX headers for popen/pclose/fread')
    edit(player, '\tCommon::String ffmpegPath = "ffmpeg";', '''\tCommon::String ffmpegPath = "ffmpeg";
#ifndef _WIN32
    if (Common::FSNode(Common::Path("/opt/homebrew/bin/ffmpeg")).exists())
        ffmpegPath = "/opt/homebrew/bin/ffmpeg";
    else if (Common::FSNode(Common::Path("/usr/local/bin/ffmpeg")).exists())
        ffmpegPath = "/usr/local/bin/ffmpeg";
#endif''')
    # Shell quoting is needed for both a configured binary and imported path.
    edit(player, 'namespace Scumm {', '''namespace Scumm {
#ifndef _WIN32
static Common::String videoShellQuote(const Common::String &value) {
    Common::String result = "'";
    for (uint i = 0; i < value.size(); ++i) {
        if (value[i] == '\\'') result += "'\\\"'\\\"'";
        else result += value[i];
    }
    return result + "'";
}
#endif''')
    start = '\t// ── POSIX: popen + fread ──────────────────────────'
    path = root / player
    text = path.read_text()
    begin = text.index(start)
    end = text.index('\n\t_hdPipePosix =', begin)
    old = text[begin:end]
    new = start + '''
    Common::String cmd = Common::String::format(
        "%s -nostdin -v error -i %s -vf scale=%d:%d:flags=bilinear -f rawvideo -pix_fmt rgba -an -",
        videoShellQuote(ffmpegPath).c_str(), videoShellQuote(mp4Path).c_str(), width, height);
'''
    edit(player, old, new)
    # Remove the POSIX hardcoded size, retaining the dimensions given by caller.
    edit(player, '\t_width = 2560;\n\t_height = 1920;\n\treturn true;\n#endif',
         '\treturn true;\n#endif')

    smush = 'engines/scumm/smush/smush_player.cpp'
    header = 'engines/scumm/smush/smush_player.h'
    # Later font patches extend these blocks. Do not reinsert the base movie
    # integration merely because its full original block no longer matches.
    (root / 'engines/scumm/hd_video_support.h').write_bytes(
        (Path(__file__).parent / 'hd_video_support.h').read_bytes())
    if '// Render decoded replacement with native subtitle coverage.' in (root / smush).read_text():
        return
    edit(smush, '#include "scumm/hd_video_player.h"',
         '#include "scumm/hd_video_player.h"\n#include "scumm/hd_video_support.h"')
    edit(header, '\tbyte *_hdFrameBuffer;', '''\tbyte *_hdFrameBuffer;
    bool _hdVideoEnded = false;
    int _hdFramesRead = 0;
    bool _hdHasSubtitles = false;
    Common::Array<byte> _hdSubtitleDark, _hdSubtitleLight;''')
    edit(smush, '\tif (_hdVideo->hasVideo(filename)) {',
         '\tif (offset == 0 && startFrame == 0 && _hdVideo->hasVideo(filename)) {')
    edit(smush, '_hdVideo->open(mp4Path, 2880, 2160)',
         '_hdVideo->open(mp4Path, _vm->_screenWidth * _vm->_hdScale, _vm->_screenHeight * _vm->_hdScale)')
    edit(smush, '\t\t\t_hdVideoActive = true;', '''\t\t\t_hdVideoActive = true;
            _hdVideoEnded = false;
            _hdFramesRead = 0;''')
    edit(smush, '\t_skipNext = false;\n\n\tif (_insanity)', '''\t_skipNext = false;
    _hdHasSubtitles = false;
    if (_hdVideoActive) {
        int count = _vm->_screenWidth * _vm->_screenHeight;
        _hdSubtitleDark.resize(count);
        _hdSubtitleLight.resize(count);
        memset(_hdSubtitleDark.data(), 0, count);
        memset(_hdSubtitleLight.data(), 255, count);
    }

\tif (_insanity)''')
    # Advance even when the native scheduler elects not to display this frame.
    # Native SAN audio and duration remain authoritative (some supplied clips
    # omit or add ten trailing black frames).
    edit(smush, '\tif (_width != 0 && _height != 0) {\n\t\tupdateScreen();', '''
    if (_hdVideoActive && !_hdVideoEnded) {
        if (_hdFrameBuffer && _hdVideo->readFrame(_hdFrameBuffer)) {
            ++_hdFramesRead;
        } else {
            _hdVideoEnded = true;
            _hdVideo->close();
            if (!_hdFramesRead) {
                warning("HD video decode failed; using original movie");
                _hdVideoActive = false;
            } else {
                warning("HD video ended after %d frames; retaining last image until native movie ends", _hdFramesRead);
            }
        }
    }
\tif (_width != 0 && _height != 0) {
\t\tupdateScreen();''')
    for method in ('drawStringWrap', 'drawString'):
        original = f'\t\tsf->{method}(str, _dst, clipRect, pos_x, pos_y, color, flg);'
        edit(smush, original, original + f'''
        if (_hdVideoActive) {{
            sf->{method}(str, _hdSubtitleDark.data(), clipRect, pos_x, pos_y, color, flg);
            sf->{method}(str, _hdSubtitleLight.data(), clipRect, pos_x, pos_y, color, flg);
            _hdHasSubtitles = true;
        }}''')
    file = root / smush
    text = file.read_text()
    marker = '// Render decoded replacement with native subtitle coverage.'
    if marker not in text:
        begin = text.index('\t\t\t\t\t\t// Render HD video frame from ffmpeg pipe')
        end = text.index('\n\t\t\t\t\t} else {', begin)
        edit(smush, text[begin:end], '''                        // Render decoded replacement with native subtitle coverage.
                        int w = _hdVideo->getWidth(), h = _hdVideo->getHeight();
                        const byte *pixels = _hdFrameBuffer;
                        if (_hdHasSubtitles) {
                            if (_hdScaleBufferSize < w * h) {
                                _hdScaleBuffer = (uint32 *)realloc(_hdScaleBuffer, w * h * 4);
                                _hdScaleBufferSize = _hdScaleBuffer ? w * h : 0;
                            }
                            if (_hdScaleBuffer) {
                                memcpy(_hdScaleBuffer, _hdFrameBuffer, w * h * 4);
                                HdVideoSupport::subtitles(_hdScaleBuffer, w, h,
                                    _hdSubtitleDark.data(), _hdSubtitleLight.data(),
                                    _vm->_screenWidth, _vm->_screenHeight, _pal);
                                pixels = (const byte *)_hdScaleBuffer;
                            }
                        }
                        _vm->_system->copyRectToScreen(pixels, w * 4, 0, 0, w, h);''')
    (root / 'engines/scumm/hd_video_support.h').write_bytes(
        (Path(__file__).parent / 'hd_video_support.h').read_bytes())
