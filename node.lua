-- StoryField Mural Display
-- Displays mural images with dissolve crossfade transitions

gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
print("MURAL: gl.setup complete")

-- Config
local dissolve_duration = 1.5

-- Image state
local current_image = nil
local old_image = nil
local transition_start = nil
local has_mural = false
print("MURAL: variables initialized")

-- Pre-created textures for test pattern (avoid per-frame allocation)
local white_dim = resource.create_colored_texture(1, 1, 1, 0.2)
local white_mid = resource.create_colored_texture(1, 1, 1, 0.5)
print("MURAL: test pattern textures created")

-- Update config when changed in dashboard
util.json_watch("config.json", function(config)
    print("MURAL: config updated")
    dissolve_duration = config.dissolve_duration or 1.5
end)
print("MURAL: config watch registered")

-- Watch for new mural images written by the service
util.file_watch("current.png", function(raw)
    print("MURAL: file_watch triggered for current.png")
    if not raw or #raw == 0 then
        print("MURAL: current.png empty or missing, skipping")
        return
    end
    -- Dispose the outgoing old image if mid-transition
    if old_image then
        old_image:dispose()
    end
    -- Current becomes old (will fade out)
    old_image = current_image
    -- Load new image (will fade in)
    current_image = resource.load_image({ file = "current.png" })
    -- Start transition
    transition_start = sys.now()
    has_mural = true
end)
print("MURAL: file_watch registered")

-- Cover scaling: fill screen, maintain aspect ratio, center crop
local function draw_cover(image, alpha)
    if not image then
        return
    end
    local img_w, img_h = image:size()
    if img_w == 0 or img_h == 0 then
        return
    end
    local screen_w = NATIVE_WIDTH
    local screen_h = NATIVE_HEIGHT
    local scale = math.max(screen_w / img_w, screen_h / img_h)
    local draw_w = img_w * scale
    local draw_h = img_h * scale
    local x = (screen_w - draw_w) / 2
    local y = (screen_h - draw_h) / 2
    image:draw(x, y, x + draw_w, y + draw_h, alpha)
end

-- Draw a visible test pattern while waiting for first mural image
local function draw_test_pattern()
    -- Dark blue background so it's clearly distinct from "broken black"
    gl.clear(0.05, 0.05, 0.2, 1)

    local w = NATIVE_WIDTH
    local h = NATIVE_HEIGHT
    local cx = w / 2
    local cy = h / 2

    -- Pulsing alpha to prove the render loop is alive
    local pulse = 0.4 + 0.3 * math.sin(sys.now() * 2)

    -- Center crosshair
    white_dim:draw(cx - 1, 0, cx + 1, h)
    white_dim:draw(0, cy - 1, w, cy + 1)

    -- Corner brackets (alignment markers for projector)
    local m = 40
    local len = 80
    local thick = 3
    -- Top-left
    white_mid:draw(m, m, m + len, m + thick)
    white_mid:draw(m, m, m + thick, m + len)
    -- Top-right
    white_mid:draw(w - m - len, m, w - m, m + thick)
    white_mid:draw(w - m - thick, m, w - m, m + len)
    -- Bottom-left
    white_mid:draw(m, h - m - thick, m + len, h - m)
    white_mid:draw(m, h - m - len, m + thick, h - m)
    -- Bottom-right
    white_mid:draw(w - m - len, h - m - thick, w - m, h - m)
    white_mid:draw(w - m - thick, h - m - len, w - m, h - m)

    -- Pulsing center dot to prove render loop is running
    local dot_size = 30
    white_mid:draw(cx - dot_size, cy - dot_size, cx + dot_size, cy + dot_size, pulse)
end

print("MURAL: render functions defined")

function node.render()
    if not has_mural then
        draw_test_pattern()
        return
    end

    gl.clear(0, 0, 0, 1)

    if transition_start then
        local elapsed = sys.now() - transition_start
        local progress = elapsed / dissolve_duration
        if progress >= 1.0 then
            -- Transition complete
            if old_image then
                old_image:dispose()
                old_image = nil
            end
            transition_start = nil
            draw_cover(current_image, 1.0)
        else
            -- Mid-transition: crossfade
            draw_cover(old_image, 1.0 - progress)
            draw_cover(current_image, progress)
        end
    else
        -- No transition in progress
        draw_cover(current_image, 1.0)
    end
end

print("MURAL: node.lua fully loaded")
