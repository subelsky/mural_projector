ZIP_NAME := storyfield-mural-display.zip

PACKAGE_FILES := \
	package.json \
	package.png \
	node.json \
	node.lua \
	service \
	hosted.lua \
	hosted.py \
	mural_poller.py \
	default.webp \
	README.md

.PHONY: build clean sdk validate

build: sdk validate
	zip $(ZIP_NAME) $(PACKAGE_FILES)

sdk:
	curl -fsSL -o hosted.lua https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.lua
	curl -fsSL -o hosted.py  https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.py

validate:
	@for f in $(PACKAGE_FILES); do \
		if [ ! -f "$$f" ]; then \
			echo "Error: required file missing: $$f"; \
			exit 1; \
		fi; \
	done

clean:
	rm -f $(ZIP_NAME) hosted.lua hosted.py
