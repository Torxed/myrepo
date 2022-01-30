# myrepo
A *(**experimental**)* tool to create your own Arch Linux repository

# Example

We'll use `cat ./packages.txt.example` as an example:
```
base
base-devel
linux
linux-firmware
```

```
sudo python -m myrepo --packages ./packages.txt.example
```

This will create a repo structure like so:
```
.
├── community
│   └── os
│       └── x86_64
│           ├── gnome-code-assistance-2:3.16.1+14+gaad6437-2-x86_64.pkg.tar.zst
│           └── gnome-code-assistance-2:3.16.1+14+gaad6437-2-x86_64.pkg.tar.zst.sig
├── core
│   └── os
│       └── x86_64
│           ├── acl-2.3.1-1-x86_64.pkg.tar.zst
│           ├── acl-2.3.1-1-x86_64.pkg.tar.zst.sig
│           ├── core.db -> core.db.tar.gz
│           ├── core.db.tar.gz
│           ├── core.db.tar.gz.old
│           ├── core.files -> core.files.tar.gz
│           ├── core.files.tar.gz
│           ├── core.files.tar.gz.old
...
├── extra
│   └── os
│       └── x86_64
│           ├── bash-completion-2.11-2-any.pkg.tar.zst
│           ├── bash-completion-2.11-2-any.pkg.tar.zst.sig
│           ├── extra.db -> extra.db.tar.gz
│           ├── extra.db.tar.gz
│           ├── extra.db.tar.gz.old
│           ├── extra.files -> extra.files.tar.gz
│           ├── extra.files.tar.gz
│           ├── extra.files.tar.gz.old
│           ├── libcroco-0.6.13-2-x86_64.pkg.tar.zst
│           ├── libcroco-0.6.13-2-x86_64.pkg.tar.zst.sig
│           ├── libgee-0.20.4-1-x86_64.pkg.tar.zst
│           ├── libgee-0.20.4-1-x86_64.pkg.tar.zst.sig
│           ├── libsysprof-capture-3.42.1-2-x86_64.pkg.tar.zst
│           ├── libsysprof-capture-3.42.1-2-x86_64.pkg.tar.zst.sig
│           ├── libxml2-2.9.12-7-x86_64.pkg.tar.zst
│           └── libxml2-2.9.12-7-x86_64.pkg.tar.zst.sig
└── testing
    └── os
        └── x86_64
```

All dependencies from the four packages will be there.
`--path` can override the base location of the repo from `/srv/repo` to somewhere else.

`--mirror-list` defaults to `/etc/pacman.d/mirrorlist` and can be overriden.
