name = renumid
version = $(shell awk '/^Version: / {print $$2}' $(name).spec)

prefix = /usr
sbindir = $(prefix)/sbin
mandir = $(datadir)/man

.PHONY: all install docs clean

all:
	@echo "Nothing to be build."

docs: all
	$(MAKE) -C docs docs

install: docs-install
#	-[ ! -f $(DESTDIR)$(sysconfdir)/dstat.conf ] && install -D -m0644 dstat.conf $(DESTDIR)$(sysconfdir)/dstat.conf
	install -Dp -m0755 renumid.py $(DESTDIR)$(sbindir)/renumid

docs-install:
	$(MAKE) -C docs install

clean:
	$(MAKE) -C docs clean

dist: clean
#	svn up && svn list -R | pax -d -w -x ustar -s ,^,$(name)-$(version)/, | bzip2 >../$(name)-$(version).tar.bz2
#	svn st -v --xml | \
#        xmlstarlet sel -t -m "/status/target/entry" -s A:T:U '@path' -i "wc-status[@revision]" -v "@path" -n | \
#        pax -d -w -x ustar -s ,^,$(name)-$(version)/, | \
#        bzip2 >../$(name)-$(version).tar.bz2

#rpm: dist
#	rpmbuild -tb --clean --rmspec --define "_rpmfilename %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm" --define "_rpmdir ../" ../$(name)-$(version).tar.bz2

#srpm: dist
#	rpmbuild -ts --clean --rmspec --define "_rpmfilename %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm" --define "_srcrpmdir ../" ../$(name)-$(version).tar.bz2
