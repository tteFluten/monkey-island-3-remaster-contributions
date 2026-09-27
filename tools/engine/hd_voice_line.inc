// Language packs (hd_language.h), per-line voices. A pack's voices/<TAG>.wav
// is served to iMUSE as a regular speech file: an iMUS header whose map has
// FRMT, the English line's SYNC blocks (lip sync), REGN and STOP, then DATA
// with the WAV's 16-bit PCM. The track therefore ends with the audio, and
// volume, pan, pause and the talking state behave as for any other line.
bool BundleMgr::openVoiceLine(Common::SeekableReadStream *wav, const Common::Array<byte> &sync) {
    _voiceLine.clear();
    if (!wav) return false;
    uint32 dataOffset = 0, dataLength = 0, rate = 0;
    uint16 format = 0, channels = 0, bits = 0;
    const uint32 riff = wav->readUint32BE();
    wav->readUint32LE();
    if (riff == MKTAG('R', 'I', 'F', 'F') && wav->readUint32BE() == MKTAG('W', 'A', 'V', 'E')) {
        while (wav->pos() + 8 <= wav->size()) {
            const uint32 id = wav->readUint32BE(), length = wav->readUint32LE();
            const int64 start = wav->pos();
            if (id == MKTAG('f', 'm', 't', ' ') && length >= 16) {
                format = wav->readUint16LE(); channels = wav->readUint16LE(); rate = wav->readUint32LE();
                wav->skip(6); bits = wav->readUint16LE();
            } else if (id == MKTAG('d', 'a', 't', 'a')) {
                dataOffset = start; dataLength = MIN<uint32>(length, wav->size() - start);
                break;
            }
            wav->seek(start + length + (length & 1));
        }
    }
    if (format != 1 || bits != 16 || channels < 1 || channels > 2 || !rate || !dataLength) {
        warning("HD voice line is not 16-bit PCM mono/stereo WAV (format %d, %d bit, %d channels)", format, bits, channels);
        delete wav;
        return false;
    }
    const uint32 syncSize = sync.size() + 28 + 16 + 12 <= 0x2000 - 8 ? sync.size() : 0;
    const uint32 mapSize = 28 + syncSize + 16 + 12, header = 24 + mapSize;
    _voiceLine.resize(header + dataLength);
    byte *out = _voiceLine.data();
    WRITE_BE_UINT32(out, MKTAG('i', 'M', 'U', 'S')); WRITE_BE_UINT32(out + 4, header - 8 + dataLength);
    WRITE_BE_UINT32(out + 8, MKTAG('M', 'A', 'P', ' ')); WRITE_BE_UINT32(out + 12, mapSize);
    byte *block = out + 16;
    WRITE_BE_UINT32(block, MKTAG('F', 'R', 'M', 'T')); WRITE_BE_UINT32(block + 4, 20); WRITE_BE_UINT32(block + 8, header);
    WRITE_BE_UINT32(block + 12, 0); WRITE_BE_UINT32(block + 16, 16); WRITE_BE_UINT32(block + 20, rate);
    WRITE_BE_UINT32(block + 24, channels);
    block += 28;
    if (syncSize) {
        memcpy(block, sync.data(), syncSize);
        for (byte *s = block; s + 12 <= block + syncSize; s += READ_BE_UINT32(s + 4) + 8)
            WRITE_BE_UINT32(s + 8, header); // Each SYNC block starts with the audio.
        block += syncSize;
    }
    WRITE_BE_UINT32(block, MKTAG('R', 'E', 'G', 'N')); WRITE_BE_UINT32(block + 4, 8);
    WRITE_BE_UINT32(block + 8, header); WRITE_BE_UINT32(block + 12, dataLength);
    block += 16;
    WRITE_BE_UINT32(block, MKTAG('S', 'T', 'O', 'P')); WRITE_BE_UINT32(block + 4, 4); WRITE_BE_UINT32(block + 8, header + dataLength);
    block += 12;
    WRITE_BE_UINT32(block, MKTAG('D', 'A', 'T', 'A')); WRITE_BE_UINT32(block + 4, dataLength);
    wav->seek(dataOffset);
    const bool read = wav->read(out + header, dataLength) == dataLength;
    delete wav;
    if (!read) { _voiceLine.clear(); return false; }
    _curDecompressedFilePos = 0;
    return true;
}
