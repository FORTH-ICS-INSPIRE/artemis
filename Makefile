BACKEND_SERVICES = autoignore autostarter configuration database detection fileobserver mitigation notifier prefixtree
TAP_SERVICES = bgpstreamhisttap bgpstreamkafkatap bgpstreamlivetap exabgptap riperistap

BUILD ?= latest

.PHONY: $(BACKEND_SERVICES)
$(BACKEND_SERVICES): # build backend container
$(BACKEND_SERVICES):
	@echo "Building $@ service for tag $(BUILD)"
	@docker pull inspiregroup/artemis-$@:latest
ifneq ($(BUILD), "latest")
	@docker pull inspiregroup/artemis-$@:$(BUILD)
endif
	@docker build -t artemis-$@:$(BUILD) --cache-from inspiregroup/artemis-$@:latest --cache-from inspiregroup/artemis-$@:$(BUILD) backend-services/$@/

.PHONY: $(TAP_SERVICES)
$(TAP_SERVICES): # build tap container
$(TAP_SERVICES):
	@echo "Building $@ service for tag $(BUILD)"
	@docker pull inspiregroup/artemis-$@:latest
ifneq ($(BUILD), "latest")
	@docker pull inspiregroup/artemis-$@:$(BUILD)
endif
	@docker build -t artemis-$@:$(BUILD) --cache-from inspiregroup/artemis-$@:latest --cache-from inspiregroup/artemis-$@:$(BUILD) monitor-services/$@/

.PHONY: build-backend
build-backend: # builds all backend containers
build-backend: $(BACKEND_SERVICES)

.PHONY: build-taps
build-taps: # builds all tap containers
build-taps: $(TAP_SERVICES)

.PHONY: build-frontend
build-frontend: # builds frontend container
build-frontend: log-message
	@docker pull inspiregroup/artemis-frontend:latest
	@docker build --build-arg revision=$(git rev-parse --short HEAD) -t artemis-frontend:$(BUILD) --cache-from inspiregroup/artemis-frontend:latest --cache-from inspiregroup/artemis-frontend:$(BUILD) frontend/

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
	@docker-compose pull
	@for service in $(BACKEND_SERVICES) $(TAP_SERVICES) frontend ; do \
		docker tag inspiregroup/artemis-$$service:$(BUILD) artemis_$$service:$(BUILD); \
	done

.PHONY: unittest
unittest: # run all unit tests
unittest:
	@for service in detection configuration ; do \
        PYTHONPATH=./backend-services/$$service/core pytest --cov=$$service --cov-append --cov-config=./testing/.coveragerc backend-services/$$service; \
    done

.PHONY: all
all: # build all
all: build-backend build-taps build-frontend

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
	@docker-compose up

.PHONY: stop
stop: # stop containers
stop:
	@docker-compose down -v --remove-orphans

.PHONY: clean
clean: # stop containers and clean volumes
clean: stop
	@sudo rm -rf postgres-data-* frontend/db/artemis_webapp.db