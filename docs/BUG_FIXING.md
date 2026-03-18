  We're building an info-beamer package for Raspberry Pi 5 that displays mural images with crossfade transitions. The package has three components:

  - node.lua — Lua rendering script (info-beamer's runtime)
  - service — Python 2.7 script that polls an API and downloads images
  - mural_poller.py — Pure Python polling logic

  The package is deployed as a zip file uploaded through the info-beamer dashboard.

  The Problem

  The node.lua script does not render anything on screen. No errors appear in logread -f. The device is a Raspberry Pi 5 running info-beamer OS.

  What We've Tried

  1. Minimal blue-screen test — WORKED. This 4-line node.lua successfully rendered a blue screen on the device:
  gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
  function node.render()
      gl.clear(0, 0, 1, 1)
  end
  2. Added util.init_hosted() — BROKE IT (black screen). Adding this single line after gl.setup() caused a black screen. We confirmed via logread -f that the error was: node error: cannot render node 'root' / You have to setup
  the node by calling gl.setup first. Root cause: we had a print() statement before gl.setup(), and info-beamer doesn't allow any output before gl.setup. After fixing the print ordering, we also discovered that
  util.init_hosted() doesn't exist in the vendored hosted.lua SDK (the SDK only exports parse_config). Removed the call entirely.
  3. Discovered info-beamer doesn't support WebP. Device logs showed [image.c] unknown file format for current.webp. info-beamer only supports JPEG and PNG. Changed all references from .webp to .png across the codebase
  (node.lua, service, tests, Makefile, CI workflows).
  4. Added print("MURAL: ...") logging probes throughout node.lua (all placed after gl.setup). Deployed the zip — no MURAL log messages appeared in logread -f at all. The node.lua doesn't appear to be loading, despite the
  package being deployed.
  5. Network issue (separate): The device can be reached via info-beamer's SSH relay, but ifconfig only shows 127.0.0.1. The service can't reach the external API. This is a device-level networking issue, not a package
  permissions issue.

  Current State of node.lua

  gl.setup(NATIVE_WIDTH, NATIVE_HEIGHT)
  print("MURAL: gl.setup complete")

  local dissolve_duration = 1.5
  local current_image = nil
  local old_image = nil
  local transition_start = nil
  local has_mural = false

  local white_dim = resource.create_colored_texture(1, 1, 1, 0.2)
  local white_mid = resource.create_colored_texture(1, 1, 1, 0.5)

  node.event("config_update", function(config)
      dissolve_duration = config.dissolve_duration or 1.5
  end)

  util.file_watch("current.png", function(raw)
      -- image loading and crossfade logic
  end)

  function node.render()
      if not has_mural then
          draw_test_pattern()  -- dark blue bg with pulsing dot
          return
      end
      -- crossfade rendering
  end

  Key Facts

  - The minimal blue-screen node.lua works on this device — so info-beamer, HDMI output, and package deployment all function.
  - The full node.lua produces a black screen with no log output whatsoever.
  - hosted.lua is vendored from https://github.com/info-beamer/package-sdk and only exports parse_config.
  - info-beamer Lua docs: https://info-beamer.com/doc/info-beamer
  - Package reference docs: https://info-beamer.com/doc/package-reference
  - The package targets "platforms": ["pi/v8"] which includes Pi 5.

  What To Investigate

  - Why does the full node.lua fail silently (no log output, no rendering) when the minimal version works?
  - Could resource.create_colored_texture(), node.event(), or util.file_watch() be crashing before node.render() is defined?
  - Is there a difference in how info-beamer loads the package when additional SDK files (hosted.lua, hosted.py) are present?
  - Should we try a binary search approach: start from the working blue-screen and add back one feature at a time until it breaks?
