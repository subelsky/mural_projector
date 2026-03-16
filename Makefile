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

LAST_TAG := $(shell git describe --tags --abbrev=0 2>/dev/null || echo v0.0)
LAST_VERSION := $(subst v,,$(LAST_TAG))
MAJOR := $(word 1,$(subst ., ,$(LAST_VERSION)))
MINOR := $(word 2,$(subst ., ,$(LAST_VERSION)))
NEXT_MINOR := $(shell echo $$(($(MINOR) + 1)))
VERSION ?= $(MAJOR).$(NEXT_MINOR)

JSON_FILES := package.json node.json

.PHONY: build clean sdk validate validate-json release

build: sdk validate
	zip $(ZIP_NAME) $(PACKAGE_FILES)

sdk:
	curl -fsSL -o hosted.lua https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.lua
	curl -fsSL -o hosted.py  https://raw.githubusercontent.com/info-beamer/package-sdk/master/hosted.py

validate-json:
	@for f in $(JSON_FILES); do \
		python -m json.tool "$$f" > /dev/null || exit 1; \
	done

validate: validate-json
	@for f in $(PACKAGE_FILES); do \
		if [ ! -f "$$f" ]; then \
			echo "Error: required file missing: $$f"; \
			exit 1; \
		fi; \
	done

release:
	@echo "Releasing v$(VERSION)..."
	git tag v$(VERSION)
	git push origin v$(VERSION)

clean:
	rm -f $(ZIP_NAME) hosted.lua hosted.py
