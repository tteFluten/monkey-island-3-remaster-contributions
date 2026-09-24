"""Direct static SVG costume loading using ScummVM's bundled NanoSVG."""
from pathlib import Path


def patch(root, edit):
    base = 'engines/scumm/hd_costume_manager'
    edit(base + '.cpp', '#include "image/png.h"', '#include "image/png.h"\n#include "scumm/quiver_svg.h"')
    edit(base + '.h', 'bool loadCostume(int akosId, int frame, Graphics::Surface &dest);',
         'bool loadCostume(int akosId, int frame, Graphics::Surface &dest, int svgWidth = 0, int svgHeight = 0);')
    edit(base + '.cpp', 'bool HdCostumeManager::loadCostume(int akosId, int frame, Graphics::Surface &dest) {',
         'bool HdCostumeManager::loadCostume(int akosId, int frame, Graphics::Surface &dest, int svgWidth, int svgHeight) {')
    edit(base + '.h', '\tbool loadPNG(', '\tbool loadSVG(const Common::String &path, int width, int height, Graphics::Surface &surf);\n\tbool loadPNG(')
    edit(base + '.h', '\tCommon::HashMap<CostumeKey, bool, CostumeKeyHash> _availableCostumes;',
         '\tCommon::HashMap<CostumeKey, bool, CostumeKeyHash> _availableCostumes;\n\tCommon::HashMap<CostumeKey, bool, CostumeKeyHash> _svgCostumes;\n\tCommon::HashMap<CostumeKey, bool, CostumeKeyHash> _failedSVGs;')
    edit(base + '.cpp', '\treturn path;\n}\n\nbool HdCostumeManager::loadPNG',
         '\tif (_svgCostumes.contains(CostumeKey{akosId, akosSub, frame})) {\n\t\tpath.erase(path.size() - 4); path += ".svg";\n\t}\n\treturn path;\n}\n\n#include "scumm/quiver_svg_load.inc"\n\nbool HdCostumeManager::loadPNG')
    edit(base + '.cpp', 'if (!name.hasPrefixIgnoreCase("LFLF_") || !name.hasSuffixIgnoreCase(".png"))',
         'if (!name.hasPrefixIgnoreCase("LFLF_") || (!name.hasSuffixIgnoreCase(".png") && !(_exactFrames && name.hasSuffixIgnoreCase(".svg"))))')
    edit(base + '.cpp', '\t\t\t_availableCostumes[key] = true;',
         '\t\t\t_availableCostumes[key] = true;\n\t\t\tif (name.hasSuffixIgnoreCase(".svg")) _svgCostumes[key] = true;')
    edit(base + '.cpp', '\t\tkeys.push_back(it->_key);',
         '\t\tif (_svgCostumes.contains(it->_key)) continue; // SVG needs actual cel dimensions at draw time\n\t\tkeys.push_back(it->_key);')
    edit(base + '.cpp', '\t\tkey.frame = loadFrame;\n\n\t\t// Check cache first', '''		key.frame = loadFrame;
		bool svg = _svgCostumes.contains(key);
		if (svg && (svgWidth <= 0 || svgHeight <= 0 || _failedSVGs.contains(key))) continue;

		// Check cache first''')
    # On-demand SVG textures are cached by cel and requested resolution. PNG
    # callers retain the existing behavior and batch decoder.
    edit(base + '.cpp', '\t\tif (cacheIt != _textureCache.end()) {\n\t\t\tdest.copyFrom', '''		if (cacheIt != _textureCache.end() && svg &&
			(cacheIt->_value.surface.w != svgWidth || cacheIt->_value.surface.h != svgHeight)) {
			cacheIt->_value.surface.free();
			_textureCache.erase(key);
			cacheIt = _textureCache.end();
		}
		if (cacheIt != _textureCache.end()) {
			dest.copyFrom''')
    edit(base + '.cpp', '\t\tif (!loadPNG(path, surf))\n\t\t\tcontinue;', '''		if (!(svg ? loadSVG(path, svgWidth, svgHeight, surf) : loadPNG(path, surf))) {
			if (svg) _failedSVGs[key] = true; // no parse/error loop every frame
			continue;
		}''')
    edit('engines/scumm/gfx.cpp', '#include "scumm/actor.h"',
         '#include "scumm/actor.h"\n#include "scumm/quiver_native.h"')
    edit('engines/scumm/gfx.cpp', '\t// Step 2: Composite game content (8-bit → 32-bit via palette) over HD background',
         '#include "scumm/quiver_prepare.inc"\n\t// Step 2: Composite game content (8-bit → 32-bit via palette) over HD background')
    edit('engines/scumm/gfx.cpp', 'uint8 curPix = visRow[sx];',
         'uint8 curPix = quiverNative.empty() ? visRow[sx] : quiverNative[sy * visW + sx];')
    edit('engines/scumm/gfx.cpp', 'uint8 curPix = srcRow[sx];',
         'uint8 curPix = quiverNative.empty() ? srcRow[sx] : quiverNative[sy * visW + sx];')
    for name in ('quiver_svg.h', 'quiver_svg_load.inc', 'quiver_prepare.inc', 'quiver_native.h'):
        (root / 'engines/scumm' / name).write_bytes((Path(__file__).parent / name).read_bytes())
