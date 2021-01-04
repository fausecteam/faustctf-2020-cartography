SERVICE := cartography
DESTDIR ?= dist_root
SERVICEDIR ?= /srv/$(SERVICE)

.PHONY: build install

build:
	$(MAKE) -C src

install: build
	mkdir -p $(DESTDIR)$(SERVICEDIR)/data
	cp src/cartography $(DESTDIR)$(SERVICEDIR)/
	mkdir -p $(DESTDIR)/etc/systemd/system
	cp src/cartography@.service $(DESTDIR)/etc/systemd/system/
	cp src/cartography.socket $(DESTDIR)/etc/systemd/system/
	cp src/system-cartography.slice $(DESTDIR)/etc/systemd/system/
