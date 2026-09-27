// Included in the OpenGL backend. Scene effects precede UI; the brief entry
// fade covers the completed canvas while leaving the later cursor pass clear.
#if !USE_FORCED_GLES
class HdRemasterGL {
    Graphics::Surface _previousUI;
    Graphics::Surface _previousWater;
    Texture *_water = nullptr;
    Shader *_waterShader = nullptr;
    ShaderPipeline *_waterPipeline = nullptr;
    TextureTarget *_waterPattern = nullptr;
    double _waterLast = 0, _waterTime = 0;
    int _waterRoom = -1;
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
    int _presentedRoom = -1;
    double _sceneFadeStarted = -1;
    Texture *_fadeBlack = nullptr;

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
    void drawExitFade(Pipeline *normal, Framebuffer *screen, int width, int height, bool overlay) {
        const float opacity = HdRemaster::state().exitFadeOpacity;
        if (opacity <= 0 || overlay) return;
        if (!_fadeBlack) {
            Graphics::Surface pixel;
            pixel.create(1, 1, Graphics::PixelFormat::createFormatRGBA32());
            *(uint32 *)pixel.getPixels() = 0xffffffff;
            upload(_fadeBlack, pixel, false);
            pixel.free();
        }
        // Cover the complete final presentation, including film and subtitles.
        // A full black hold also hides viewport changes during movie release.
        normal->setFramebuffer(screen); normal->activate();
        screen->enableScissorTest(false);
        screen->enableBlend(Framebuffer::kBlendModePremultipliedTransparency);
        normal->setColor(0, 0, 0, opacity);
        normal->drawTexture(*_fadeBlack, 0, 0, width, height);
        normal->setColor(1, 1, 1, 1);
        screen->enableBlend(Framebuffer::kBlendModeOpaque);
        screen->enableScissorTest(true);
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
uniform sampler2D shaderTexture, backgroundTexture, blurTexture, coverageTexture, curveTexture, waterTexture, waterPatternTexture;
uniform sampler2D reflectionTexture;
uniform vec4 backgroundRect, canvasRect, coverageRect;
uniform vec4 focusRect, blurRect;
uniform vec4 reflectionRect;
uniform vec2 reflectionTexel;
uniform vec2 reflectionPlane; // intercept and slope in reflection texture coordinates
uniform vec4 waterPatternRect;
uniform vec4 waterPalette; // Original room color and its blend with the painting.
uniform vec2 waterTexel;
uniform float waterEnabled, waterSurface;
uniform vec4 waterTuning; // opacity, distortion, highlights, mirrored background opacity
uniform vec4 waterColorLight; // RGB palette multipliers and direct light strength
uniform vec4 waterLight; // light direction XYZ and highlight exponent
uniform vec4 vignette; // enabled, amount, inner radius, softness
uniform float saturation, dofIntensity, backgroundOnly;
vec3 waterSky(vec3 direction, vec3 palette) {
    float t = clamp(direction.y * 0.5 + 0.5, 0.0, 1.0);
    // Reflect the room's water palette instead of the demo's bright blue sky.
    return mix(palette * 1.65 + vec3(0.025, 0.04, 0.035), palette * 1.1, t);
}
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
    vec2 bgUV = backgroundRect.xy + uv * backgroundRect.zw;
    float visibility = mix(1.0 - scene.a, 1.0, backgroundOnly);
    float focus = 0.0;
    if (dofIntensity > 0.0) {
        focus = texture2D(coverageTexture, focusRect.xy + uv * focusRect.zw).r * dofIntensity;
        float amount = focus * visibility;
        rgb += (texture2D(blurTexture, blurRect.xy + uv * blurRect.zw).rgb - texture2D(backgroundTexture, bgUV).rgb) * amount;
    }
    if (waterEnabled > 0.0) {
        float coverage = texture2D(waterTexture, coverageRect.xy + uv * coverageRect.zw).r;
        float depth = coverage * 255.0;
        float mask = waterSurface > 0.5 ? smoothstep(0.0, 2.5, depth) : coverage;
        float amount = mask * visibility * (1.0 - focus) * waterTuning.x;
        if (amount > 0.001) {
            // Height and normals come from the small GPU wave target. Reflect
            // and light them at presentation resolution for sharp highlights.
            vec4 pattern = texture2D(waterPatternTexture, waterPatternRect.xy + uv * waterPatternRect.zw);
            float calmEdge = waterSurface > 0.5 ? smoothstep(2.0, 16.0, depth) : 1.0;
            vec3 normal = normalize(mix(vec3(0.0, 1.0, 0.0), pattern.rgb * 2.0 - 1.0, calmEdge));
            vec2 offset = normal.xz * vec2(3.5, 1.75) * waterTexel * mask * waterTuning.y;
            vec3 base = texture2D(backgroundTexture, bgUV).rgb;
            vec3 painted = texture2D(backgroundTexture, bgUV + offset).rgb;
            vec3 palette = mix(painted, waterPalette.rgb, waterPalette.a) * waterColorLight.rgb;
            float viewHeight = waterSurface > 0.5 ? mix(0.3, 0.9, clamp(depth / 160.0, 0.0, 1.0)) : 0.65;
            vec3 view = normalize(vec3(0.0, viewHeight, 1.0));
            vec3 light = normalize(waterLight.xyz);
            float diffuse = clamp(dot(normal, light), 0.0, 1.0);
            float fresnel = mix(0.16, 0.9, pow(1.0 - clamp(dot(normal, view), 0.0, 1.0), 3.0));
            vec3 reflection = waterSky(reflect(-view, normal), palette);
            // Give moving crests/troughs readable contrast without lifting
            // the whole painted surface or weakening shoreline coverage.
            vec3 body = palette * (0.72 + 0.65 * pattern.a);
            vec3 water = mix(body * (0.8 + 0.25 * diffuse * waterColorLight.a), reflection, fresnel);
            if (waterSurface > 0.5) {
                // Mirror the painting around one continuous water plane.
                // The detailed coverage mask must not bend the reflected hull.
                // Keep its opacity separate
                // from wave lighting so stronger ripples don't make a solid
                // mirrored hull. Never sample actors or UI.
                vec2 reflectionUV = reflectionRect.xy + uv * reflectionRect.zw;
                float mirrorY = reflectionPlane.x + reflectionPlane.y * reflectionUV.x;
                reflectionUV.y = 2.0 * mirrorY - reflectionUV.y;
                reflectionUV += normal.xz * vec2(24.0, 5.0) * calmEdge * waterTuning.y * reflectionTexel;
                reflectionUV = clamp(reflectionUV, reflectionTexel * 0.5, vec2(1.0) - reflectionTexel * 0.5);
                vec3 mirroredBackground = texture2D(reflectionTexture, reflectionUV).rgb * vec3(0.72, 0.86, 0.9) * waterColorLight.rgb;
                water = mix(water, mirroredBackground, waterTuning.w);
            }
            float specular = pow(clamp(dot(normal, normalize(light + view)), 0.0, 1.0), waterLight.w);
            vec3 highlight = mix(palette / max(max(palette.r, max(palette.g, palette.b)), 0.04), vec3(1.0), 0.25);
            water += highlight * specular * 0.42 * waterTuning.z * waterColorLight.a;
            water = mix(base, water, calmEdge);
            rgb += (water - base) * amount;
        }
    }
    gl_FragColor = vec4(grade(rgb), 1.0) * color;
}
)GLSL";
        // Adapted from the user-supplied fcGSW1 source: five noise octaves plus
        // a detail wave. Analytic derivatives reuse the same noise corners for
        // height and normals, avoiding four extra finite-difference evaluations.
        // The demo's flying camera/sky/fog do not replace the painted room.
        const char *waterPattern = R"GLSL(
varying vec2 uv;
varying vec4 color;
uniform vec4 waterWorld;
uniform vec2 waterSampleStep;
uniform float waterSeconds;
uniform float waterWaveStrength;
uniform float waterWaveScale;
vec4 waterHash(vec4 n) {
    return fract(sin(n) * 43333.333);
}
// Returns value and the two spatial derivatives; the third dimension is time.
vec3 waterNoise(vec3 p) {
    vec3 cell = floor(p), f = fract(p);
    vec3 u = f * f * (3.0 - 2.0 * f);
    vec2 du = 6.0 * f.xy * (1.0 - f.xy);
    float n = dot(cell, vec3(1.0, 55.0, 120.0));
    vec4 lower = waterHash(n + vec4(0.0, 1.0, 55.0, 56.0));
    vec4 upper = waterHash(n + vec4(120.0, 121.0, 175.0, 176.0));
    vec4 rows = mix(vec4(lower.xz, upper.xz), vec4(lower.yw, upper.yw), u.x);
    float value = mix(mix(rows.x, rows.y, u.y), mix(rows.z, rows.w, u.y), u.z);
    float dx = mix(mix(lower.y - lower.x, lower.w - lower.z, u.y),
                   mix(upper.y - upper.x, upper.w - upper.z, u.y), u.z) * du.x;
    float dy = mix(rows.y - rows.x, rows.w - rows.z, u.z) * du.y;
    return vec3(value, dx, dy);
}
void main() {
    vec2 p = waterWorld.xy + uv * waterWorld.zw;
    vec2 flow = p / (vec2(52.0, 28.0) * waterWaveScale) - vec2(0.08, 0.35) * waterSeconds;
    vec3 wave = vec3(0.35, 0.0, 0.0);
    float frequency = 0.45, timeFrequency = 0.15, amplitude = 0.45;
    float footprint = max(waterSampleStep.x, waterSampleStep.y) / waterWaveScale;
    for (int octave = 0; octave < 5; ++octave) {
        vec3 sampleWave = waterNoise(vec3(flow * frequency, waterSeconds * timeFrequency));
        // Fade unresolved detail before upscaling to avoid sparkling/aliasing.
        float weight = 1.0 - smoothstep(0.25, 0.75, footprint * frequency);
        wave += amplitude * weight * vec3(sampleWave.x - 0.5, sampleWave.yz * frequency);
        frequency *= 2.0; timeFrequency *= 2.0; amplitude *= 0.5;
    }
    vec3 detail = waterNoise(vec3(flow * 1.8, waterSeconds * 0.4));
    wave += 0.12 * vec3(detail.x, detail.yz * 1.8);
    vec3 normal = normalize(vec3(-wave.y * 1.8 * waterWaveStrength, 1.0, -wave.z * 1.8 * waterWaveStrength));
    // RGB: encoded normal, A: wave height; no alpha blending on this target.
    float height = 0.35 + (wave.x - 0.35) * waterWaveStrength;
    gl_FragColor = vec4(normal * 0.5 + 0.5, clamp(height, 0.0, 1.0)) * color;
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
        _effect = new Shader(); _blurShader = new Shader(); _maskShader = new Shader(); _waterShader = new Shader();
        if (!_effect->loadFromStrings("comi-remaster-effects", vertex, fragment, attributes, 120) ||
            !_blurShader->loadFromStrings("comi-remaster-blur", vertex, blur, attributes, 120) ||
            !_maskShader->loadFromStrings("comi-remaster-coverage", vertex, mask, attributes, 120) ||
            !_waterShader->loadFromStrings("comi-remaster-water", vertex, waterPattern, attributes, 120)) {
            warning("COMI GPU effects unavailable; retaining CPU effects");
            delete _effect; delete _blurShader; delete _maskShader; _effect = _blurShader = _maskShader = nullptr;
            delete _waterShader; _waterShader = nullptr;
            _attempted = true; return;
        }
        _effects = new ShaderPipeline(_effect); _blurPipeline = new ShaderPipeline(_blurShader);
        _maskPipeline = new ShaderPipeline(_maskShader); _maskShader->setUniform("shaderTexture", 0);
        _waterPipeline = new ShaderPipeline(_waterShader); _waterPipeline->setColor(1,1,1,1);
        _effect->setUniform("shaderTexture", 0); _effect->setUniform("backgroundTexture", 1);
        _effect->setUniform("blurTexture", 2); _effect->setUniform("coverageTexture", 3);
        _effect->setUniform("curveTexture", 4); _blurShader->setUniform("shaderTexture", 0);
        _effect->setUniform("waterTexture", 5);
        _effect->setUniform("waterPatternTexture", 6);
        _effect->setUniform("reflectionTexture", 7);
        _maskPipeline->setColor(1,1,1,1); _effects->setColor(1,1,1,1); _blurPipeline->setColor(1,1,1,1);
        _canvas = new TextureTarget(); _blur[0] = new TextureTarget(); _blur[1] = new TextureTarget();
        _cover[0] = new TextureTarget(); _cover[1] = new TextureTarget();
        _wideBlur[0] = new TextureTarget(); _wideBlur[1] = new TextureTarget();
        _waterPattern = new TextureTarget();
        for (auto *target : {_canvas, _blur[0], _blur[1], _cover[0], _cover[1], _wideBlur[0], _wideBlur[1], _waterPattern}) {
            target->enableBlend(Framebuffer::kBlendModeDisabled);
            target->enableScissorTest(false);
            target->getTexture()->enableLinearFiltering(true);
        }
        HdRemaster::state().available = true;
    }
    void destroy() {
        delete _fadeBlack; _fadeBlack = nullptr;
        HdRemaster::state().available = HdRemaster::state().active = false;
        _lastPipeline = nullptr; _lastScreen = nullptr;
        Pipeline::disable();
        if (_queries[0]) GL_CALL(glDeleteQueries(8, _queries));
        memset(_queries, 0, sizeof(_queries)); memset(_pending, 0, sizeof(_pending));
        delete _effects; delete _blurPipeline; delete _maskPipeline;
        _effects = _blurPipeline = _maskPipeline = nullptr; _effect = _blurShader = _maskShader = nullptr;
        delete _ui; _ui = nullptr; _previousUI.free();
        delete _water; _water = nullptr; _previousWater.free();
        delete _waterPipeline; _waterPipeline = nullptr; _waterShader = nullptr;
        delete _waterPattern; _waterPattern = nullptr;
        _waterLast = _waterTime = 0; _waterRoom = -1;
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
        const bool wideFocus = wide && canvasW == 2560 && s.viewportWidth == 640;
        const Math::Vector4d frameRect(float(left)/canvasW, 0, float(gameW)/canvasW, 1);
        const double waterNow = HdRemaster::milliseconds();
        if (_waterRoom != s.room) { _waterRoom = s.room; _waterTime = 0; _waterLast = 0; }
        const bool animateWater = s.water && !s.waterPaused && !overlay;
        if (animateWater && _waterLast && waterNow - _waterLast < 100)
            _waterTime += (waterNow - _waterLast) * 0.001 * s.waterSpeed / 100.0;
        _waterLast = waterNow;
        // Value noise is not periodic: keep elapsed seconds rather than wrapping
        // a phase, which would visibly jump the moving surface every minute.
        const bool sceneChanged = _generation != s.generation;
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
            if (s.water) {
                const auto &mask = s.waterCoverage;
                const bool resized = _previousWater.w != mask.w || _previousWater.h != mask.h;
                if (!_water) _water = new Texture(GL_LUMINANCE, GL_LUMINANCE, GL_UNSIGNED_BYTE);
                if (resized || memcmp(_previousWater.getPixels(), mask.getPixels(), mask.pitch * mask.h)) {
                    _water->setSize(mask.w, mask.h); _water->enableLinearFiltering(true);
                    _water->updateArea(Common::Rect(mask.w, mask.h), mask);
                    // Surface storage is reused after the first allocation.
                    if (resized) { _previousWater.free(); _previousWater.create(mask.w, mask.h, mask.format); }
                    memcpy(_previousWater.getPixels(), mask.getPixels(), mask.pitch * mask.h);
                }
            }
            if (s.dof || s.water) {
                const auto &bg = *s.background;
                const bool changed = _backgroundPixels != bg.getPixels() || _room != s.room || _revision != s.revision;
                if (changed) {
                    _backgroundPixels = bg.getPixels(); _room = s.room; _revision = s.revision; _radius = -1;
                    if (_bgBpp != bg.format.bytesPerPixel) { delete _background; _background = nullptr; }
                    _bgBpp = bg.format.bytesPerPixel;
                    upload(_background, bg);
                }
                if (s.dof && _radius != s.radius) {
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
                if (s.dof && (_coverageGeneration != s.coverageGeneration || !_coverage)) {
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
                bind(_background, 1);
                if (s.dof) { bind(_blur[0]->getTexture(), 2); bind(_cover[0]->getTexture(), 3); }
                _effect->setUniform("backgroundRect", Math::Vector4d(float(s.backgroundX)/bg.w, float(s.backgroundY)/bg.h,
                    float(s.scene.w)/bg.w, float(s.scene.h)/bg.h));
            }
            if (wideFocus && s.dof &&
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
        }
        // Water advances using cached textures on presentation frames between
        // native cels. Scene/UI uploads and blur caches stay on the path above.
        if (sceneChanged || animateWater) {
            if (s.water) {
                // Half-native resolution (427x240 in 16:9), reused every frame.
                // One continuous world-space pattern spans the center and sides.
                // Its alpha stores data, so blending must remain disabled.
                const int patternW = (canvasW + 5) / 6, patternH = canvasH / 6;
                _waterPattern->setSize(patternW, patternH);
                _waterPipeline->setFramebuffer(_waterPattern); _waterPipeline->activate();
                _waterShader->setUniform1f("waterSeconds", _waterTime);
                _waterShader->setUniform1f("waterWaveStrength", s.waterWaves / 100.0f);
                _waterShader->setUniform1f("waterWaveScale", s.waterScale / 100.0f);
                _waterShader->setUniform("waterWorld", Math::Vector4d(float(s.backgroundX)/s.scale - float(left)/3,
                    float(s.backgroundY)/s.scale, float(canvasW)/3, s.viewportHeight));
                _waterShader->setUniform("waterSampleStep", Math::Vector2d(float(canvasW)/(3 * patternW * 52),
                    float(s.viewportHeight)/(patternH * 28)));
                _waterPipeline->drawTexture(*_scene, 0, 0, patternW, patternH);
                bind(_waterPattern->getTexture(), 6);
            }
            bind(_lut, 4);
            if (s.water) bind(_water, 5);
            // Keep one full-width reflection source across both drawing passes.
            // The center's working texture remains separate for native masks/DoF.
            const bool wideReflection = wide && canvasW == 2560 && s.viewportWidth == 640;
            if (s.water) bind(wideReflection ? &wide->getGLTexture() : _background, 7);
            // Express the same native-space plane in the full 16:9 texture or
            // the fallback background; both center and side passes share it.
            _effect->setUniform("reflectionPlane", wideReflection
                ? Math::Vector2d((s.waterReflectionIntercept - s.waterReflectionSlope * left / 3.0f) / s.viewportHeight,
                    s.waterReflectionSlope * canvasW / (3.0f * s.viewportHeight))
                : Math::Vector2d(s.waterReflectionIntercept * s.scale / s.background->h,
                    s.waterReflectionSlope * s.background->w / s.background->h));
            _effect->setUniform1f("waterEnabled", s.water ? 1 : 0);
            _effect->setUniform1f("waterSurface", s.waterSurface ? 1 : 0);
            _effect->setUniform("waterTuning", Math::Vector4d(s.waterOpacity / 100.0f,
                s.waterDistortion / 100.0f, s.waterHighlights / 100.0f,
                HdWater::fullSurface(s.room) ? s.waterReflection / 100.0f : 0));
            _effect->setUniform("waterColorLight", Math::Vector4d(s.waterRed / 100.0f,
                s.waterGreen / 100.0f, s.waterBlue / 100.0f, s.waterLight / 100.0f));
            const double lightAngle = s.waterLightDirection * 0.017453292519943295;
            const float lightSin = sin(lightAngle), lightCos = cos(lightAngle);
            _effect->setUniform("waterLight", Math::Vector4d(0.6f * lightCos + 0.35f * lightSin,
                0.85f, 0.6f * lightSin - 0.35f * lightCos, 48.0f * s.waterGloss / 100.0f));
            // The cannon sea shares room 11's #0F3333 water treatment. Other rooms keep
            // their own painted palette; artwork and saved Scene Look stay intact.
            _effect->setUniform("waterPalette", HdWater::fullSurface(s.room)
                ? Math::Vector4d(15.0f/255, 51.0f/255, 51.0f/255, 0.65f)
                : Math::Vector4d(0, 0, 0, 0));
            _canvas->setSize(canvasW, canvasH);
            _effects->setFramebuffer(_canvas); _effects->activate();
            GL_CALL(glClear(GL_COLOR_BUFFER_BIT));
            if (wide && canvasW == 2560 && s.viewportWidth == 640) {
                _effect->setUniform1f("dofIntensity", s.dof ? s.intensity / 100.0f : 0);
                _effect->setUniform1f("backgroundOnly", 1);
                _effect->setUniform("canvasRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("backgroundRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("reflectionRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("reflectionTexel", Math::Vector2d(3.0f/canvasW, 3.0f/canvasH));
                // Focus spans the full painting; water retains its native boundary mapping.
                _effect->setUniform("focusRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("blurRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("coverageRect", Math::Vector4d(-float(left)/gameW,0,float(canvasW)/gameW,1));
                if (s.dof || s.water) bind(&wide->getGLTexture(), 1);
                if (s.dof) { bind(_wideBlur[0]->getTexture(), 2); bind(_cover[0]->getTexture(), 3); }
                _effect->setUniform("waterPatternRect", Math::Vector4d(0,0,1,1));
                _effect->setUniform("waterTexel", Math::Vector2d(3.0f/canvasW, 3.0f/canvasH));
                _effects->drawTexture(wide->getGLTexture(), 0, 0, canvasW, canvasH);
            }
            _effect->setUniform1f("backgroundOnly", 0);
            _effect->setUniform("coverageRect", Math::Vector4d(0,0,1,1));
            _effect->setUniform("focusRect", wideFocus ? frameRect : Math::Vector4d(0,0,1,1));
            if (s.dof || s.water) {
                bind(_background, 1);
                const Math::Vector4d bgRect(float(s.backgroundX)/s.background->w, float(s.backgroundY)/s.background->h,
                    float(s.scene.w)/s.background->w, float(s.scene.h)/s.background->h);
                if (s.dof) {
                    // Sample the same full-width blur in both passes, preventing
                    // a clamped 4:3 blur edge through the middle of the painting.
                    bind(wideFocus ? _wideBlur[0]->getTexture() : _blur[0]->getTexture(), 2);
                    bind(_cover[0]->getTexture(), 3);
                }
                _effect->setUniform("backgroundRect", bgRect);
                _effect->setUniform("blurRect", wideFocus ? frameRect : bgRect);
            }
            _effect->setUniform1f("dofIntensity", s.dof ? s.intensity / 100.0f : 0);
            _effect->setUniform("waterPatternRect", Math::Vector4d(float(left)/canvasW,0,float(gameW)/canvasW,1));
            _effect->setUniform("waterTexel", Math::Vector2d(float(s.scale)/s.background->w, float(s.scale)/s.background->h));
            _effect->setUniform("reflectionRect", wideReflection
                ? Math::Vector4d(float(left)/canvasW, 0, float(gameW)/canvasW, 1)
                : Math::Vector4d(float(s.backgroundX)/s.background->w, float(s.backgroundY)/s.background->h,
                    float(s.scene.w)/s.background->w, float(s.scene.h)/s.background->h));
            _effect->setUniform("reflectionTexel", wideReflection
                ? Math::Vector2d(3.0f/canvasW, 3.0f/canvasH)
                : Math::Vector2d(float(s.scale)/s.background->w, float(s.scale)/s.background->h));
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
        // Reveal the completed chapter card/cannon/post-movie scene together, rather than animating
        // individual PNG palettes. Start AFTER its first composition/uploads;
        // loading time must not consume or lengthen this presentation-only fade.
        const double fadeNow = HdRemaster::milliseconds();
        const bool movieReveal = s.movieFadePending && !overlay && !s.exitFadeActive;
        if (_presentedRoom != s.room || movieReveal) {
            _presentedRoom = s.room;
            _sceneFadeStarted = (HdRemaster::chapterCard(s.room) || s.room == 9 || movieReveal) ? fadeNow : -1;
            if (movieReveal) {
                s.movieFadePending = false;
                s.exitFadeOpacity = 0;
            }
        }
        float sceneGain = 1.0f;
        if (_sceneFadeStarted >= 0) {
            const float progress = CLIP(float((fadeNow - _sceneFadeStarted) / 1000.0), 0.0f, 1.0f);
            sceneGain = progress * progress * (3.0f - 2.0f * progress);
            if (progress >= 1.0f) _sceneFadeStarted = -1;
        }
        // This includes background, side extensions, costumes and scene UI.
        // Keep cached pixels untouched; restore white before drawing the cursor.
        normal->setColor(sceneGain, sceneGain, sceneGain, 1.0f);
        normal->drawTexture(*_canvas->getTexture(), x, gameRect.top, w, h);
        normal->setColor(1.0f, 1.0f, 1.0f, 1.0f);
        screen->enableScissorTest(true);
        return true;
    }
};
#else
class HdRemasterGL {
public:
    bool snapshot(Graphics::Surface &) { return false; }
    void drawExitFade(Pipeline *, Framebuffer *, int, int, bool) {}
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
