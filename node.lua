-- StoryField Mural Display
-- Displays mural images with dissolve crossfade transitions

gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
util.init_hosted()

-- Config
local dissolve_duration = 1.5

-- Image state
local current_image = resource.load_image("default.webp")
local old_image = nil
local transition_start = nil

-- Update config when changed in dashboard
node.event("config_update", function(config)
    dissolve_duration = config.dissolve_duration or 1.5
end)

-- Watch for new mural images written by the service
util.file_watch("current.webp", function(raw)
    -- Dispose the outgoing old image if mid-transition
    if old_image then
        old_image:dispose()
    end
    -- Current becomes old (will fade out)
    old_image = current_image
    -- Load new image (will fade in)
    current_image = resource.load_image{ file = "current.webp" }
    -- Start transition
    transition_start = sys.now()
end)

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

function node.render()
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
