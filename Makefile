.PHONY: check test build package installer

check:
	./scripts/audit-release.sh

test:
	./scripts/test-readonly-refresh.sh

build:
	./scripts/build-native.sh

package:
	./scripts/package-native.sh

installer:
	./scripts/package-installer.sh
