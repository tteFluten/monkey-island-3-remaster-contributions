"""Reject damaged speech headers before interpreting their compression table."""

BEFORE = '''	_file->seek(_bundleTable[index].offset, SEEK_SET);
	uint32 tag = _file->readUint32BE();

	if (tag == MKTAG('i','M','U','S')) {
		_isUncompressed = true;
		return true;
	}

	_numCompItems = _file->readUint32BE();
	assert(_numCompItems > 0);
	_file->seek(4, SEEK_CUR);
	_lastBlockDecompressedSize = _file->readUint32BE();
	if (tag != MKTAG('C','O','M','P')) {
		debug("BundleMgr::loadCompTable() Compressed sound %d (%s:%d) invalid (%s)", index, _file->getDebugName().c_str(), _bundleTable[index].offset, tag2str(tag));
		return false;
	}
'''

AFTER = '''	// Invalid bundle entries are unavailable audio, not fatal engine errors.
	// Check the tag before interpreting arbitrary payload bytes as a block count.
	const int32 entrySize = _bundleTable[index].size;
	const int32 entryOffset = _bundleTable[index].offset;
	if (entryOffset < 0 || entrySize < 16 ||
		(int64)entryOffset + entrySize > _file->size() ||
		!_file->seek(entryOffset, SEEK_SET)) {
		warning("Skipping truncated bundled audio %s in %s", _bundleTable[index].filename, _file->getDebugName().c_str());
		return false;
	}
	uint32 tag = _file->readUint32BE();
	if (tag == MKTAG('i','M','U','S')) {
		_isUncompressed = true;
		return true;
	}
	if (tag != MKTAG('C','O','M','P')) {
		warning("Skipping invalid bundled audio %s in %s (tag %s)", _bundleTable[index].filename, _file->getDebugName().c_str(), tag2str(tag));
		return false;
	}

	_numCompItems = _file->readUint32BE();
	// Each compression-table record occupies 16 bytes after a 16-byte header.
	if (_numCompItems <= 0 || _numCompItems > (entrySize - 16) / 16) {
		warning("Skipping invalid compression table for %s in %s", _bundleTable[index].filename, _file->getDebugName().c_str());
		_numCompItems = 0;
		return false;
	}
	_file->seek(4, SEEK_CUR);
	_lastBlockDecompressedSize = _file->readUint32BE();
'''


def patch(root, edit):
    edit('engines/scumm/imuse_digi/dimuse_bndmgr.cpp', BEFORE, AFTER)
