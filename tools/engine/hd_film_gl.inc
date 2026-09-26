// Final presentation only: never feed the processed image back into scene caches.
#if !USE_FORCED_GLES
class HdFilmGL {
    Shader *_shader = nullptr;
    ShaderPipeline *_pipeline = nullptr;
    Texture *_frame = nullptr;
    bool _attempted = false;
    uint _revision = 0;

    void initialize() {
        if (_attempted) return;
        _attempted = true;
        if (!OpenGLContext.shadersSupported || !OpenGLContext.NPOTSupported) return;
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
uniform sampler2D shaderTexture;
uniform vec2 textureSize;
uniform vec4 contentRect;
uniform float filmTick, amount, pixelScale;
uniform vec4 filmTuning; // grain, dust, scratches, exposure flicker
uniform float filmWobble, filmChromatic;
varying vec2 uv;
varying vec4 color;
float hash(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}
float softGrain(vec2 p) {
    vec2 cell = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(cell), hash(cell + vec2(1.0, 0.0)), f.x),
               mix(hash(cell + vec2(0.0, 1.0)), hash(cell + vec2(1.0)), f.x), f.y) * 2.0 - 1.0;
}
void main() {
    vec2 pixel = uv * textureSize;
    vec4 original = texture2D(shaderTexture, uv);
    // Leave presentation bars and encoded movie black untouched.
    if (pixel.x < contentRect.x || pixel.y < contentRect.y ||
        pixel.x >= contentRect.z || pixel.y >= contentRect.w ||
        max(original.r, max(original.g, original.b)) < 0.001) {
        gl_FragColor = original * color; return;
    }
    float seconds = filmTick / 24.0;
    // At strength 20: <0.5px displacement at 1440p, smoothly varying gate weave.
    vec2 weave = vec2(sin(seconds * 1.7) + 0.35 * sin(seconds * 4.1),
                      cos(seconds * 1.3) + 0.3 * sin(seconds * 3.3));
    vec2 samplePixel = clamp(pixel + weave * (0.22 * amount * pixelScale * filmWobble),
                             contentRect.xy + 0.5, contentRect.zw - 0.5);
    vec3 rgb = texture2D(shaderTexture, samplePixel / textureSize).rgb;
    if (filmChromatic > 0.0) {
        // Film-channel misregistration covers the entire composited picture,
        // including costumes near the center, with a little extra at the edges.
        vec2 halfFrame = max((contentRect.zw - contentRect.xy) * 0.5, vec2(1.0));
        vec2 lens = (pixel - (contentRect.xy + contentRect.zw) * 0.5) / halfFrame;
        float edge = clamp(dot(lens, lens) * 0.5, 0.0, 1.0);
        vec2 fringe = vec2(1.0, 0.15) * mix(0.55, 1.0, edge)
            * (amount * filmChromatic * pixelScale);
        vec2 redPixel = clamp(samplePixel + fringe, contentRect.xy + 0.5, contentRect.zw - 0.5);
        vec2 bluePixel = clamp(samplePixel - fringe, contentRect.xy + 0.5, contentRect.zw - 0.5);
        rgb.r = texture2D(shaderTexture, redPixel / textureSize).r;
        rgb.b = texture2D(shaderTexture, bluePixel / textureSize).b;
    }
    float luma = dot(rgb, vec3(0.299, 0.587, 0.114));
    float taper = smoothstep(0.0, 0.08, luma) * (1.0 - smoothstep(0.92, 1.0, luma));
    vec2 p = pixel / pixelScale;
    // Two grain sizes remain visible at normal Retina viewing distance. Bound
    // the temporal seed so long sessions retain fine-pixel hash precision.
    vec2 seedOffset = vec2(mod(filmTick, 256.0) * 37.0, mod(floor(filmTick / 256.0), 256.0) * 53.0);
    float coarse = softGrain(p / 2.0 + seedOffset);
    float fine = hash(floor(p) + seedOffset + 271.0) * 2.0 - 1.0;
    float exposure = 0.0015 * sin(seconds * 3.1) + 0.001 * sin(seconds * 7.7);
    rgb += taper * amount * ((coarse * 5.0 + fine * 2.0) / 255.0 * filmTuning.x + rgb * exposure * filmTuning.w);
    // Sparse small motes on a jittered grid, replaced with each film frame.
    vec2 cell = floor(p / 96.0);
    float seed = hash(cell + seedOffset);
    vec2 center = vec2(hash(cell + seedOffset + 13.0), hash(cell + seedOffset + 71.0)) * 88.0 + 4.0;
    float dust = (1.0 - smoothstep(0.7, 2.6, length(mod(p, 96.0) - center))) * step(0.985, seed);
    // About one brief fine scratch every few seconds, with irregular gaps.
    float scratchSeed = hash(vec2(floor(filmTick / 3.0), 91.0));
    float scratchX = mix(contentRect.x, contentRect.z, hash(vec2(floor(filmTick / 3.0), 37.0))) / pixelScale;
    float scratch = (1.0 - smoothstep(0.3, 1.3, abs(p.x - scratchX))) * step(0.96, scratchSeed);
    scratch *= smoothstep(0.3, 0.7, hash(vec2(floor(p.y / 36.0), floor(filmTick / 3.0))));
    rgb -= taper * amount * (dust * 0.055 * filmTuning.y + scratch * 0.03 * filmTuning.z);
    gl_FragColor = vec4(clamp(rgb, 0.0, 1.0), original.a) * color;
}
)GLSL";
        _shader = new Shader();
        if (!_shader->loadFromStrings("comi-vintage-film", vertex, fragment, attributes, 120)) {
            warning("COMI film shader unavailable; retaining unfiltered presentation");
            delete _shader; _shader = nullptr; return;
        }
        _pipeline = new ShaderPipeline(_shader);
        _pipeline->setColor(1, 1, 1, 1);
        _shader->setUniform("shaderTexture", 0);
        _frame = new Texture(GL_RGBA, GL_RGBA, GL_UNSIGNED_BYTE);
        _frame->enableLinearFiltering(true);
        _frame->setWrapMode(kWrapModeEdge);
        _frame->setFlip(true); // glCopyTexSubImage2D stores bottom row first.
    }
    static void capture(const char *name, const GLint *viewport) {
        Graphics::Surface pixels;
        pixels.create(viewport[2], viewport[3], Graphics::PixelFormat::createFormatRGBA32());
        GL_CALL(glReadPixels(viewport[0], viewport[1], pixels.w, pixels.h,
                            GL_RGBA, GL_UNSIGNED_BYTE, pixels.getPixels()));
        // PNG rows are top-down; GL readbacks are bottom-up.
        for (int y = 0; y < pixels.h / 2; ++y)
            for (int x = 0; x < pixels.w; ++x)
                SWAP(*(uint32 *)pixels.getBasePtr(x, y), *(uint32 *)pixels.getBasePtr(x, pixels.h - y - 1));
        Common::DumpFile file;
        if (file.open(Common::Path(ConfMan.get("playtest_session") + name))) Image::writePNG(file, pixels);
        pixels.free();
    }
public:
    bool needsRedraw() {
        const bool changed = _revision != HdFilm::state().revision;
        _revision = HdFilm::state().revision;
        return changed || HdFilm::state().capture ||
            (HdFilm::enabled() && HdFilm::strength() > 0 && (!_attempted || _pipeline));
    }
    void destroy() {
        if (_pipeline) Pipeline::disable();
        delete _pipeline; _pipeline = nullptr; _shader = nullptr;
        delete _frame; _frame = nullptr; _attempted = false;
    }
    void draw(Pipeline *normal, Framebuffer *screen, const Common::Rect &gameRect,
              int width, int height, bool overlay, bool wide) {
        const bool captureRequested = HdFilm::state().capture;
        HdFilm::state().capture = false;
        const bool active = HdFilm::enabled() && HdFilm::strength() > 0;
        if ((!active && !captureRequested) || !normal || !screen || width <= 0 || height <= 0) return;
        normal->setFramebuffer(screen); normal->activate();
        GLint viewport[4]; GL_CALL(glGetIntegerv(GL_VIEWPORT, viewport));
        if (viewport[2] <= 0 || viewport[3] <= 0) return;
        if (captureRequested) capture("/film-before.png", viewport);
        if (active) {
            initialize();
            if (_pipeline && _frame->setSize(viewport[2], viewport[3])) {
                GL_CALL(glActiveTexture(GL_TEXTURE0));
                _frame->bind();
                GL_CALL(glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, viewport[0], viewport[1], viewport[2], viewport[3]));
                float left = gameRect.left, right = gameRect.right;
                float top = gameRect.top, bottom = gameRect.bottom;
                if (overlay) { left = top = 0; right = width; bottom = height; }
                else if ((HdRemaster::state().active || wide) && ConfMan.getInt("hd_aspect_ratio") == 169) {
                    const float w = gameRect.height() * 16.0f / 9.0f;
                    left = gameRect.left + (gameRect.width() - w) * 0.5f; right = left + w;
                }
                const float sx = float(viewport[2]) / width, sy = float(viewport[3]) / height;
                _pipeline->setFramebuffer(screen); _pipeline->activate();
                screen->enableScissorTest(false);
                screen->enableBlend(Framebuffer::kBlendModeDisabled);
                _shader->setUniform("textureSize", Math::Vector2d(viewport[2], viewport[3]));
                _shader->setUniform("contentRect", Math::Vector4d(MAX(0.0f, left * sx), MAX(0.0f, (height - bottom) * sy),
                    MIN(float(viewport[2]), right * sx), MIN(float(viewport[3]), (height - top) * sy)));
                const uint32 now = g_system->getMillis();
                const float tick = HdFilm::state().testTick >= 0 ? HdFilm::state().testTick :
                    float((now / 1000u) % 3600u * 24u + (now % 1000u) * 24u / 1000u);
                _shader->setUniform1f("filmTick", tick);
                _shader->setUniform1f("amount", HdFilm::strength() / 20.0f);
                _shader->setUniform("filmTuning", Math::Vector4d(HdFilm::get(HdFilm::kGrain) / 100.0f,
                    HdFilm::get(HdFilm::kDust) / 100.0f, HdFilm::get(HdFilm::kScratches) / 100.0f,
                    HdFilm::get(HdFilm::kFlicker) / 100.0f));
                _shader->setUniform1f("filmWobble", HdFilm::get(HdFilm::kWobble) / 100.0f);
                _shader->setUniform1f("filmChromatic", HdFilm::get(HdFilm::kChromatic) / 100.0f);
                _shader->setUniform1f("pixelScale", MAX(0.5f, (bottom - top) * sy / 1440.0f));
                _pipeline->drawTexture(*_frame, 0, 0, width, height);
                normal->setFramebuffer(screen); normal->activate();
                screen->enableBlend(Framebuffer::kBlendModeOpaque);
            }
        }
        if (captureRequested) capture("/film-after.png", viewport);
    }
};
#else
class HdFilmGL {
public:
    bool needsRedraw() { return false; }
    void destroy() {}
    void draw(Pipeline *, Framebuffer *, const Common::Rect &, int, int, bool, bool) {}
};
#endif
static HdFilmGL &hdFilmGL() { static HdFilmGL renderer; return renderer; }
