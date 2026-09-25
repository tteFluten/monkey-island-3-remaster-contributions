// Included in the OpenGL backend. Every effect runs before the UI/cursor pass.
#if !USE_FORCED_GLES
class HdRemasterGL {
    Graphics::Surface _previousUI;
    Pipeline *_lastPipeline = nullptr;
    Framebuffer *_lastScreen = nullptr;
    Shader *_effect = nullptr, *_blurShader = nullptr, *_maskShader = nullptr;
    ShaderPipeline *_effects = nullptr, *_blurPipeline = nullptr, *_maskPipeline = nullptr;
    Texture *_ui = nullptr, *_scene = nullptr, *_background = nullptr, *_coverage = nullptr, *_lut = nullptr;
    TextureTarget *_wideBlur[2] = {nullptr, nullptr};
    Surface *_wideSource = nullptr;
    int _wideRadius = -1, _wideRoom = -1, _wideRevision = -1;
    TextureTarget *_cover[2] = {nullptr, nullptr};
    TextureTarget *_canvas = nullptr, *_blur[2] = {nullptr, nullptr};
    const void *_backgroundPixels = nullptr;
    int _room = -1, _revision = -1, _radius = -1, _bgBpp = 0;
    uint _generation = ~0u, _coverageGeneration = ~0u;
    HdColorGrade::Grade _grade;
    GLuint _queries[8] = {};
    bool _pending[8] = {}, _queryActive = false;
    uint _querySamples[8] = {}, _querySerial = 0, _querySlot = 0;
    double _cpuStarted = 0;
    bool _hasGrade = false, _attempted = false;

    static void upload(Texture *&texture, const Graphics::Surface &pixels, bool linear = true) {
        if (!texture) {
            const int format = pixels.format.bytesPerPixel == 3 ? GL_RGB : GL_RGBA;
            texture = new Texture(GL_RGBA, format, GL_UNSIGNED_BYTE);
        }
        texture->setSize(pixels.w, pixels.h);
        texture->enableLinearFiltering(linear);
        texture->updateArea(Common::Rect(pixels.w, pixels.h), pixels);
    }
    static void bind(const Texture *texture, int unit) {
        GL_CALL(glActiveTexture(GL_TEXTURE0 + unit));
        texture->bind();
        GL_CALL(glActiveTexture(GL_TEXTURE0));
    }
public:
    bool snapshot(Graphics::Surface &pixels) {
        if (!_canvas || !_lastPipeline || !HdRemaster::state().active) return false;
        HdRemaster::resize(pixels, _canvas->getTexture()->getWidth(), _canvas->getTexture()->getHeight());
        _lastPipeline->setFramebuffer(_canvas); _lastPipeline->activate();
        GL_CALL(glReadPixels(0, 0, pixels.w, pixels.h, GL_RGBA, GL_UNSIGNED_BYTE, pixels.getPixels()));
        _lastPipeline->setFramebuffer(_lastScreen); _lastPipeline->activate();
        return true;
    }
    void beginFrame() {
        _cpuStarted = HdRemaster::milliseconds();
        auto &s = HdRemaster::state();
        if (!s.recording || !glGetQueryObjectui64v || !glBeginQuery) return;
        if (_querySerial != s.recordSerial) {
            if (_queries[0]) GL_CALL(glDeleteQueries(8, _queries));
            memset(_queries, 0, sizeof(_queries)); memset(_pending, 0, sizeof(_pending));
            _querySerial = s.recordSerial;
        }
        if (!_queries[0]) GL_CALL(glGenQueries(8, _queries));
        for (uint i = 0; i < 8; ++i) if (_pending[i]) {
            GLuint ready = 0; GL_CALL(glGetQueryObjectuiv(_queries[i], GL_QUERY_RESULT_AVAILABLE, &ready));
            if (ready) {
                GLuint64 ns = 0; GL_CALL(glGetQueryObjectui64v(_queries[i], GL_QUERY_RESULT, &ns));
                if (_querySamples[i] < s.sampleCount) s.samples[_querySamples[i]].gpu = ns / 1000000.0;
                _pending[i] = false;
            }
        }
        for (uint i = 0; i < 8; ++i) if (!_pending[i]) {
            _querySlot = i; _querySamples[i] = s.sampleCount; _queryActive = true;
            GL_CALL(glBeginQuery(GL_TIME_ELAPSED, _queries[i])); break;
        }
    }
    void endFrame() {
        if (_queryActive) {
            GL_CALL(glEndQuery(GL_TIME_ELAPSED)); _pending[_querySlot] = true; _queryActive = false;
        }
        HdRemaster::state().cpuBackend += HdRemaster::milliseconds() - _cpuStarted;
        HdRemaster::state().cpuWork += HdRemaster::milliseconds() - _cpuStarted;
    }
    void initialize() {
        if (_attempted) return;
        _attempted = true;
        if (!OpenGLContext.shadersSupported || !OpenGLContext.framebufferObjectSupported || !OpenGLContext.NPOTSupported) return;
        static const char *attributes[] = {"position", "texCoordIn", "blendColorIn", nullptr};
        const char *vertex = R"GLSL(
attribute vec4 position;
attribute vec2 texCoordIn;
attribute vec4 blendColorIn;
uniform mat4 projection;
varying vec2 uv;
varying vec4 color;
void main() { uv = texCoordIn; color = blendColorIn; gl_Position = projection * position; }
)GLSL";
        const char *fragment = R"GLSL(
varying vec2 uv;
varying vec4 color;
uniform sampler2D shaderTexture, backgroundTexture, blurTexture, coverageTexture, curveTexture;
uniform vec4 backgroundRect, canvasRect, coverageRect;
uniform vec4 vignette; // enabled, amount, inner radius, softness
uniform float saturation, dofIntensity, backgroundOnly;
vec3 grade(vec3 rgb) {
    vec3 v = floor(clamp(rgb, 0.0, 1.0) * 255.0 + 0.5);
    v = floor(vec3(texture2D(curveTexture, vec2((v.r + 0.5) / 256.0, 0.5)).r,
                   texture2D(curveTexture, vec2((v.g + 0.5) / 256.0, 0.5)).g,
                   texture2D(curveTexture, vec2((v.b + 0.5) / 256.0, 0.5)).b) * 255.0 + 0.5);
    float luma = floor(dot(v, vec3(77.0, 150.0, 29.0)) / 256.0);
    v = clamp(luma + floor((v - luma) * saturation / 256.0), 0.0, 255.0);
    vec2 p = (canvasRect.xy + uv * canvasRect.zw) * 2.0 - 1.0;
    float inner = vignette.z, outer = inner + vignette.w;
    float t = clamp((dot(p,p) - inner*inner) / max(0.0001, outer*outer-inner*inner), 0.0, 1.0);
    float gain = floor(255.0 * (1.0 - vignette.x * vignette.y * t*t*(3.0-2.0*t)) + 0.5);
    return floor((v * gain + 127.0) / 255.0) / 255.0;
}
void main() {
    vec4 scene = texture2D(shaderTexture, uv);
    vec3 rgb = scene.rgb;
    if (dofIntensity > 0.0) {
        vec2 bgUV = backgroundRect.xy + uv * backgroundRect.zw;
        float amount = texture2D(coverageTexture, coverageRect.xy + uv * coverageRect.zw).r * dofIntensity * mix(1.0 - scene.a, 1.0, backgroundOnly);
        rgb += (texture2D(blurTexture, bgUV).rgb - texture2D(backgroundTexture, bgUV).rgb) * amount;
    }
    gl_FragColor = vec4(grade(rgb), 1.0) * color;
}
)GLSL";
        const char *blur = R"GLSL(
varying vec2 uv;
varying vec4 color;
uniform sampler2D shaderTexture;
uniform vec2 stepSize;
uniform int radius;
void main() {
    vec3 sum = vec3(0.0);
    for (int i = -24; i <= 24; ++i) {
        if (i >= -radius && i <= radius) sum += texture2D(shaderTexture, uv + float(i)*stepSize).rgb;
    }
    gl_FragColor = vec4(floor(sum * (255.0 / float(2*radius+1)) + 0.5) / 255.0, 1.0) * color;
}
)GLSL";
        const char *mask = R"GLSL(
varying vec2 uv;
varying vec4 color;
uniform sampler2D shaderTexture;
uniform vec2 screenSize, packedSize;
uniform int planes, depth, bitOffset;
void main() {
    vec2 pixel = floor(uv * screenSize);
    float bitX = pixel.x + float(bitOffset);
    float weight = exp2(7.0 - mod(bitX, 8.0));
    float count = 0.0;
    for (int z = 0; z < 7; ++z) {
        if (z < planes) {
            vec2 sampleUV = vec2(floor(bitX / 8.0) + 0.5, pixel.y + float(z)*screenSize.y + 0.5) / packedSize;
            float maskByte = floor(texture2D(shaderTexture, sampleUV).r * 255.0 + 0.5);
            count += mod(floor(maskByte / weight), 2.0);
        }
    }
    float range = float(planes - depth + 1);
    float value = count < float(depth) ? 0.0 : floor((255.0*(count-float(depth)+1.0) + floor(range/2.0)) / range);
    gl_FragColor = vec4(vec3(value/255.0), 1.0) * color;
}
)GLSL";
        _effect = new Shader(); _blurShader = new Shader(); _maskShader = new Shader();
        if (!_effect->loadFromStrings("comi-remaster-effects", vertex, fragment, attributes, 120) ||
            !_blurShader->loadFromStrings("comi-remaster-blur", vertex, blur, attributes, 120) ||
            !_maskShader->loadFromStrings("comi-remaster-coverage", vertex, mask, attributes, 120)) {
            warning("COMI GPU effects unavailable; retaining CPU effects");
            delete _effect; delete _blurShader; delete _maskShader; _effect = _blurShader = _maskShader = nullptr;
            _attempted = true; return;
        }
        _effects = new ShaderPipeline(_effect); _blurPipeline = new ShaderPipeline(_blurShader);
        _maskPipeline = new ShaderPipeline(_maskShader); _maskShader->setUniform("shaderTexture", 0);
        _effect->setUniform("shaderTexture", 0); _effect->setUniform("backgroundTexture", 1);
        _effect->setUniform("blurTexture", 2); _effect->setUniform("coverageTexture", 3);
        _effect->setUniform("curveTexture", 4); _blurShader->setUniform("shaderTexture", 0);
        _maskPipeline->setColor(1,1,1,1); _effects->setColor(1,1,1,1); _blurPipeline->setColor(1,1,1,1);
        _canvas = new TextureTarget(); _blur[0] = new TextureTarget(); _blur[1] = new TextureTarget();
        _cover[0] = new TextureTarget(); _cover[1] = new TextureTarget();
        _wideBlur[0] = new TextureTarget(); _wideBlur[1] = new TextureTarget();
        for (auto *target : {_canvas, _blur[0], _blur[1], _cover[0], _cover[1], _wideBlur[0], _wideBlur[1]}) {
            target->enableBlend(Framebuffer::kBlendModeDisabled);
            target->enableScissorTest(false);
            target->getTexture()->enableLinearFiltering(true);
        }
        HdRemaster::state().available = true;
    }
    void destroy() {
        HdRemaster::state().available = HdRemaster::state().active = false;
        _lastPipeline = nullptr; _lastScreen = nullptr;
        Pipeline::disable();
        if (_queries[0]) GL_CALL(glDeleteQueries(8, _queries));
        memset(_queries, 0, sizeof(_queries)); memset(_pending, 0, sizeof(_pending));
        delete _effects; delete _blurPipeline; delete _maskPipeline;
        _effects = _blurPipeline = _maskPipeline = nullptr; _effect = _blurShader = _maskShader = nullptr;
        delete _ui; _ui = nullptr; _previousUI.free();
        delete _scene; delete _background; delete _coverage; delete _lut;
        _scene = _background = _coverage = _lut = nullptr;
        delete _wideBlur[0]; delete _wideBlur[1]; _wideBlur[0] = _wideBlur[1] = nullptr;
        _wideSource = nullptr; _wideRadius = -1;
        delete _canvas; delete _blur[0]; delete _blur[1]; delete _cover[0]; delete _cover[1];
        _canvas = _blur[0] = _blur[1] = _cover[0] = _cover[1] = nullptr;
        _attempted = _hasGrade = false; _generation = ~0u; _backgroundPixels = nullptr; _radius = -1;
    }
    bool draw(Pipeline *normal, Framebuffer *screen, Surface *ui, Surface *wide,
              const Common::Rect &gameRect, int width, int height, bool overlay) {
        auto &s = HdRemaster::state();
        if (!s.active || !s.available || !s.ui || !s.scene.getPixels() || !s.background) return false;
        _lastPipeline = normal; _lastScreen = screen;
        const int canvasW = ConfMan.getInt("hd_aspect_ratio") == 169 ? 2560 : 1920;
        const int canvasH = 1440;
        const int gameW = s.viewportWidth * 3, left = (canvasW - gameW) / 2;
        if (_generation != s.generation) {
            _generation = s.generation;
            upload(_scene, s.scene);
            if (!_ui || _previousUI.w != s.overlay->w || _previousUI.h != s.overlay->h) {
                upload(_ui, *s.overlay);
                HdRemaster::resize(_previousUI, s.overlay->w, s.overlay->h);
                memcpy(_previousUI.getPixels(), s.overlay->getPixels(), s.overlay->pitch * s.overlay->h);
            } else {
                const auto rows = HdUIUpload::changed((const byte *)_previousUI.getPixels(), _previousUI.pitch,
                    (const byte *)s.overlay->getPixels(), s.overlay->pitch, s.overlay->w * 4, s.overlay->h);
                if (rows.bottom > rows.top) {
                    _ui->updateArea(Common::Rect(0, rows.top, s.overlay->w, rows.bottom), *s.overlay);
                    memcpy(_previousUI.getBasePtr(0, rows.top), s.overlay->getBasePtr(0, rows.top),
                        (rows.bottom - rows.top) * s.overlay->pitch);
                }
            }
            if (!_hasGrade || memcmp(s.grade.value, _grade.value, sizeof(_grade.value))) {
                _hasGrade = true; _grade = s.grade;
                HdColorGrade::Lut curve; HdColorGrade::build(_grade, curve);
                uint32 pixels[256];
                for (int i = 0; i < 256; ++i)
                    pixels[i] = curve.channel[0][i] | (curve.channel[1][i] << 8) | (curve.channel[2][i] << 16) | 0xff000000u;
                Graphics::Surface lut; lut.init(256, 1, 1024, pixels, Graphics::PixelFormat::createFormatRGBA32());
                upload(_lut, lut, false);
                _effect->setUniform1f("saturation", curve.saturation);
            }
            _effect->setUniform("vignette", Math::Vector4d(_grade.value[6], _grade.value[7]/100.0f,
                _grade.value[8]/100.0f, _grade.value[9]/100.0f));
            bind(_lut, 4);
            if (s.dof) {
                const auto &bg = *s.background;
                const bool changed = _backgroundPixels != bg.getPixels() || _room != s.room || _revision != s.revision;
                if (changed) {
                    _backgroundPixels = bg.getPixels(); _room = s.room; _revision = s.revision; _radius = -1;
                    if (_bgBpp != bg.format.bytesPerPixel) { delete _background; _background = nullptr; }
                    _bgBpp = bg.format.bytesPerPixel;
                    upload(_background, bg);
                }
                if (_radius != s.radius) {
                    _radius = s.radius;
                    const int factor = MAX(1, s.scale / 2), bw = (bg.w + factor - 1) / factor, bh = (bg.h + factor - 1) / factor;
                    _blur[0]->setSize(bw, bh); _blur[1]->setSize(bw, bh);
                    // Downsample then reproduce the CPU's three separable box passes.
                    normal->setFramebuffer(_blur[0]); normal->activate();
                    normal->drawTexture(*_background, 0, 0, bw, bh);
                    for (int pass = 0; pass < 6; ++pass) {
                        _blurPipeline->setFramebuffer(_blur[(pass + 1) % 2]); _blurPipeline->activate();
                        _blurShader->setUniform("radius", (s.radius + factor/2) / factor);
                        _blurShader->setUniform("stepSize", Math::Vector2d(pass % 2 ? 0 : 1.0f/bw, pass % 2 ? 1.0f/bh : 0));
                        _blurPipeline->drawTexture(*_blur[pass % 2]->getTexture(), 0, 0, bw, bh);
                    }
                }
                if (_coverageGeneration != s.coverageGeneration || !_coverage) {
                    upload(_coverage, s.coverage, false); _coverageGeneration = s.coverageGeneration;
                    const int cw = s.viewportWidth, ch = s.viewportHeight;
                    _cover[0]->setSize(cw, ch); _cover[1]->setSize(cw, ch);
                    _maskPipeline->setFramebuffer(_cover[0]); _maskPipeline->activate();
                    _maskShader->setUniform("screenSize", Math::Vector2d(cw, ch));
                    _maskShader->setUniform("packedSize", Math::Vector2d(s.coverage.w, s.coverage.h));
                    _maskShader->setUniform("planes", s.maskPlanes); _maskShader->setUniform("depth", s.maskDepth);
                    _maskShader->setUniform("bitOffset", s.maskOffset);
                    _maskPipeline->drawTexture(*_coverage, 0, 0, cw, ch);
                    if (s.maskEdge) for (int pass = 0; pass < 2; ++pass) {
                        _blurPipeline->setFramebuffer(_cover[(pass + 1) % 2]); _blurPipeline->activate();
                        _blurShader->setUniform("radius", s.maskEdge);
                        _blurShader->setUniform("stepSize", Math::Vector2d(pass ? 0 : 1.0f/cw, pass ? 1.0f/ch : 0));
                        _blurPipeline->drawTexture(*_cover[pass]->getTexture(), 0, 0, cw, ch);
                    }
                }
                bind(_background, 1); bind(_blur[0]->getTexture(), 2); bind(_cover[0]->getTexture(), 3);
                _effect->setUniform("backgroundRect", Math::Vector4d(float(s.backgroundX)/bg.w, float(s.backgroundY)/bg.h,
                    float(s.scene.w)/bg.w, float(s.scene.h)/bg.h));
            }
            if (wide && s.dof && canvasW == 2560 &&
                (_wideSource != wide || _wideRoom != s.room || _wideRevision != s.revision || _wideRadius != s.radius)) {
                _wideSource = wide; _wideRoom = s.room; _wideRevision = s.revision; _wideRadius = s.radius;
                const int bw = 1280, bh = 720;
                _wideBlur[0]->setSize(bw, bh); _wideBlur[1]->setSize(bw, bh);
                normal->setFramebuffer(_wideBlur[0]); normal->activate();
                normal->drawTexture(wide->getGLTexture(), 0, 0, bw, bh);
                for (int pass = 0; pass < 6; ++pass) {
                    _blurPipeline->setFramebuffer(_wideBlur[(pass + 1) % 2]); _blurPipeline->activate();
                    _blurShader->setUniform("radius", (s.radius * 3 / s.scale + 1) / 2);
                    _blurShader->setUniform("stepSize", Math::Vector2d(pass % 2 ? 0 : 1.0f/bw, pass % 2 ? 1.0f/bh : 0));
                    _blurPipeline->drawTexture(*_wideBlur[pass % 2]->getTexture(), 0, 0, bw, bh);
                }
            }
            _canvas->setSize(canvasW, canvasH);
            _effects->setFramebuffer(_canvas); _effects->activate();
            GL_CALL(glClear(GL_COLOR_BUFFER_BIT));
            if (wide && canvasW == 2560 && s.viewportWidth == 640) {
                _effect->setUniform1f("dofIntensity", s.dof ? s.intensity / 100.0f : 0);
                _effect->setUniform1f("backgroundOnly", 1);
                _effect->setUniform("canvasRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("backgroundRect", Math::Vector4d(0,0,1,1));
                // Extend the original left/right depth boundary into decorative scenery.
                _effect->setUniform("coverageRect", Math::Vector4d(-float(left)/gameW,0,float(canvasW)/gameW,1));
                if (s.dof) { bind(&wide->getGLTexture(), 1); bind(_wideBlur[0]->getTexture(), 2); }
                _effects->drawTexture(wide->getGLTexture(), 0, 0, canvasW, canvasH);
            }
            _effect->setUniform1f("backgroundOnly", 0);
            _effect->setUniform("coverageRect", Math::Vector4d(0,0,1,1));
            if (s.dof) {
                bind(_background, 1); bind(_blur[0]->getTexture(), 2);
                _effect->setUniform("backgroundRect", Math::Vector4d(float(s.backgroundX)/s.background->w, float(s.backgroundY)/s.background->h,
                    float(s.scene.w)/s.background->w, float(s.scene.h)/s.background->h));
            }
            _effect->setUniform1f("dofIntensity", s.dof ? s.intensity / 100.0f : 0);
            _effect->setUniform("canvasRect", (wide || s.viewportWidth > 640)
                ? Math::Vector4d(float(left)/canvasW,0,float(gameW)/canvasW,1)
                : Math::Vector4d(0,0,1,1));
            _effects->drawTexture(*_scene, left, 0, gameW, canvasH);
            normal->setFramebuffer(_canvas); normal->activate();
            _canvas->enableBlend(Framebuffer::kBlendModePremultipliedTransparency);
            normal->drawTexture(*_ui, left, 0, gameW, canvasH);
            _canvas->enableBlend(Framebuffer::kBlendModeDisabled);
        }
        if (s.compareReady) {
            s.compareReady = false;
            Graphics::Surface pixels; pixels.create(canvasW, canvasH, Graphics::PixelFormat::createFormatRGBA32());
            auto capture = [&](const char *name) {
                GL_CALL(glReadPixels(0, 0, canvasW, canvasH, GL_RGBA, GL_UNSIGNED_BYTE, pixels.getPixels()));
                Common::DumpFile file;
                if (file.open(Common::Path(ConfMan.get("playtest_session") + name))) Image::writePNG(file, pixels);
            };
            normal->setFramebuffer(_canvas); normal->activate();
            capture("/effects-gpu.png");
            Texture *reference = nullptr; upload(reference, s.reference);
            normal->drawTexture(*reference, left, 0, gameW, canvasH);
            capture("/effects-cpu.png");
            delete reference; pixels.free();
            _generation = ~0u; // Repaint the GPU canvas on the next presentation.
        }
        normal->setFramebuffer(screen); normal->activate();
        screen->enableScissorTest(false);
        // The same centered game rectangle also drives inverse mouse mapping.
        const float h = gameRect.height(), w = h * canvasW / canvasH;
        const float x = gameRect.left + (gameRect.width() - w) * 0.5f;
        normal->drawTexture(*_canvas->getTexture(), x, gameRect.top, w, h);
        screen->enableScissorTest(true);
        return true;
    }
};
#else
class HdRemasterGL {
public:
    bool snapshot(Graphics::Surface &) { return false; }
    void beginFrame() {}
    void endFrame() {}
    void initialize() {}
    void destroy() {}
    bool draw(Pipeline *, Framebuffer *, Surface *, Surface *, const Common::Rect &, int, int, bool) { return false; }
};
#endif
static HdRemasterGL &hdRemasterGL() {
    static HdRemasterGL renderer;
    HdRemaster::state().capture = [](Graphics::Surface &pixels) { return hdRemasterGL().snapshot(pixels); };
    return renderer;
}
