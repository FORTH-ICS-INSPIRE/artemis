BACKEND_SERVICES ?= autoignore autostarter configuration database detection fileobserver mitigation notifier prefixtree
TAP_SERVICES ?= bgpstreamhisttap bgpstreamkafkatap bgpstreamlivetap exabgptap riperistap
FRONTEND_SERVICES ?= frontend

SERVICES ?= $(BACKEND_SERVICES) + $(TAP_SERVICES) + $(FRONTEND_SERVICES)

PUSH ?= false
BUILD_TAG ?= latest
CONTAINER_REPO ?= docker.io/inspiregroup
RELEASE ?= latest

.PHONY: $(BACKEND_SERVICES)
$(BACKEND_SERVICES): # build backend container
$(BACKEND_SERVICES):
	@echo "Building $@ service for tag $(BUILD_TAG)"
	@docker pull $(CONTAINER_REPO)/artemis-$@:latest || true
ifneq ($(BUILD_TAG), "latest")
	@docker pull $(CONTAINER_REPO)/artemis-$@:$(BUILD_TAG) || true
endif
	@docker build -t artemis-$@:$(BUILD_TAG) \
		--cache-from $(CONTAINER_REPO)/artemis-$@:latest \
		--cache-from $(CONTAINER_REPO)/artemis-$@:$(BUILD_TAG) \
		backend-services/$@/
ifeq ($(PUSH), "true")
	@docker tag artemis-$@:$(BUILD_TAG) $(CONTAINER_REPO)/artemis-$@:${BUILD_TAG}
	@docker push $(CONTAINER_REPO)/artemis-$@:${BUILD_TAG}
endif

.PHONY: $(TAP_SERVICES)
$(TAP_SERVICES): # build tap container
$(TAP_SERVICES):
	@echo "Building $@ service for tag $(BUILD_TAG)"
	@docker pull $(CONTAINER_REPO)/artemis-$@:latest || true
ifneq ($(BUILD_TAG), "latest")
	@docker pull $(CONTAINER_REPO)/artemis-$@:$(BUILD_TAG) || true
endif
	@docker build -t artemis-$@:$(BUILD_TAG) \
		--cache-from $(CONTAINER_REPO)/artemis-$@:latest \
		--cache-from $(CONTAINER_REPO)/artemis-$@:$(BUILD_TAG) \
		monitor-services/$@/
ifeq ($(PUSH), "true")
	@docker tag artemis-$@:$(BUILD_TAG) $(CONTAINER_REPO)/artemis-$@:${BUILD_TAG}
	@docker push $(CONTAINER_REPO)/artemis-$@:${BUILD_TAG}
endif

.PHONY: $(FRONTEND_SERVICES)
$(FRONTEND_SERVICES): # build frontend container
$(FRONTEND_SERVICES):
	@echo "Building $@ service for tag $(BUILD_TAG)"
	@docker pull $(CONTAINER_REPO)/artemis-$@:latest || true
ifneq ($(BUILD_TAG), "latest")
	@docker pull $(CONTAINER_REPO)/artemis-$@:$(BUILD_TAG) || true
endif
	@docker build --build-arg revision=$(git rev-parse --short HEAD) \
		-t artemis-frontend:$(BUILD_TAG) \
		--cache-from $(CONTAINER_REPO)/artemis-frontend:latest \
		--cache-from $(CONTAINER_REPO)/artemis-frontend:$(BUILD_TAG) frontend/
ifeq ($(PUSH), "true")
	@docker tag artemis-$@:$(BUILD_TAG) $(CONTAINER_REPO)/artemis-$@:${BUILD_TAG}
	@docker push $(CONTAINER_REPO)/artemis-temp$@:${BUILD_TAG}
endif

.PHONY: build-backend
build-backend: # builds all backend containers
build-backend: $(BACKEND_SERVICES)

.PHONY: build-taps
build-taps: # builds all tap containers
build-taps: $(TAP_SERVICES)

.PHONY: build-frontend
build-frontend: # builds frontend container
build-frontend: $(FRONTEND_SERVICES)

.PHONY: migration-check
migration-check: # checks if migration is not broken
migration-check:
	@wget -q -O postgres-data-current.tar.gz --no-check-certificate 'https://docs.google.com/uc?export=download&id=1UwtIp7gF5uO5PfhTbOAMPpDLJ4H55m7a'
	@tar xzf postgres-data-current.tar.gz
	@docker-compose up -d postgres
	@sleep 10
	@docker-compose logs postgres | grep "database system is ready to accept connections"
	@docker-compose down -v --remove-orphans && sudo rm -rf postgres-data-current*

.PHONY: verify-configuration
verify-configuration: # verify that configuration variables are changed correctly
verify-configuration:
	@python other/verify_script.py

.PHONE: setup-dev
setup-dev: # pull all images and tag them for local development
setup-dev:
	@for service in $(SERVICES) ; do \
  		@docker-compose pull $$service
		docker tag $(CONTAINER_REPO)/artemis-$$service:$(BUILD_TAG) artemis_$$service:latest; \
	done
	@if [ ! -d "local_configs" ]; then \
		mkdir -p local_configs && \
		mkdir -p local_configs/backend && \
		mkdir -p local_configs/monitor && \
		mkdir -p local_configs/frontend && \
		cp -rn backend-services/configs/* local_configs/backend && \
		cp -rn monitor-services/configs/* local_configs/monitor && \
		cp -rn frontend/webapp/configs/* local_configs/frontend; \
	fi

.PHONE: setup-routinator
setup-routinator: # create needed configuration for routinator
setup-routinator:
	@mkdir -p local_configs/routinator/tals
	@sudo chown -R 1012:1012 local_configs/routinator/tals
	@mkdir -p local_configs/routinator/rpki-repo
	@sudo chown -R 1012:1012 local_configs/routinator/rpki-repo
	@cp other/routinator/routinator.conf local_configs/routinator/routinator.conf
	@sudo chown -R 1012:1012 local_configs/routinator/routinator.conf

.PHONY: unittest
unittest: # run all unit tests
unittest:
	@for service in detection configuration ; do \
        PYTHONPATH=./backend-services/$$service/core pytest --cov=$$service --cov-append --cov-config=./testing/.coveragerc backend-services/$$service; \
    done

.PHONY: build
build: # build all
build: $(SERVICES)

.PHONY: start
start: # start local setup
start:
	@if [ ! -d "local_configs" ]; then \
		mkdir -p local_configs && \
		mkdir -p local_configs/backend && \
		mkdir -p local_configs/monitor && \
		mkdir -p local_configs/frontend && \
		cp -rn backend-services/configs/* local_configs/backend && \
		cp -rn monitor-services/configs/* local_configs/monitor && \
		cp -rn frontend/webapp/configs/* local_configs/frontend; \
	fi
	@docker-compose up -d

.PHONY: stop
stop: # stop containers
stop:
	@docker-compose down -v --remove-orphans

.PHONY: clean-db
clean-db: # stop containers and clean volumes
clean-db: stop
	@sudo rm -rf postgres-data-* frontend/db/artemis_webapp.db

.PHONY: release
release: # pull and tag images for a new release
release:
ifneq ($(BUILD_TAG), "latest")
	@for service in $(SERVICES) ; do \
		@docker $(CONTAINER_REPO)/artemis-$$service:latest \
		@docker tag $(CONTAINER_REPO)/artemis-$$service:latest $(CONTAINER_REPO)/artemis-$$service:$(RELEASE) \
		@docker push $(CONTAINER_REPO)/artemis-$$service:$(RELEASE); \
	done
else
	@echo "Provide the release to tag and push (i.e 'RELEASE=v1.2.3 make release')"
endif
