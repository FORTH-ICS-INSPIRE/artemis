#!/usr/bin/env python3
import re
import unittest

ENV_FILE = ".env"
TABLES_VERSION_FILE = "other/db/data/tables.sql"
TABLES_TEST_VERSION_FILE = "testing/detection/db/data/tables.sql"
K8S_VALUES_FILE = "artemis-chart/values.yaml"
CONFIGMAP_FILE = "artemis-chart/templates/configmap.yaml"
COMPOSE_FILE = "docker-compose.yaml"
DEPLOYMENT_FILE = "artemis-chart/templates/{}-deployment.yaml"


def get_match_from_file(fp, query):
    with open(fp, "r") as f:
        content = "".join(f.readlines())
        m = re.search(query, content)
        return m.group(1)


def get_matches_from_file(fp, query):
    with open(fp, "r") as f:
        content = "".join(f.readlines())
        m = re.findall(query, content)
        return m


class TestStringMethods(unittest.TestCase):
    def test_db_version(self):
        version = get_match_from_file(ENV_FILE, r"DB_VERSION=([0-9]*)")
        tables_version = get_match_from_file(
            TABLES_VERSION_FILE, r"upgraded_on\) VALUES \(([0-9]*)"
        )
        tables_test_version = get_match_from_file(
            TABLES_TEST_VERSION_FILE, r"upgraded_on\) VALUES \(([0-9]*)"
        )
        k8s_version = get_match_from_file(K8S_VALUES_FILE, r"dbVersion: ([0-9]*)")
        configmap_version = get_match_from_file(
            CONFIGMAP_FILE, r"\.Values\.dbVersion \| default \"([0-9]*)\""
        )

        self.assertEqual(
            version,
            tables_version,
            "Wrong db version in {}".format(TABLES_VERSION_FILE),
        )
        self.assertEqual(
            version,
            tables_test_version,
            "Wrong db version in {}".format(TABLES_TEST_VERSION_FILE),
        )
        self.assertEqual(
            version, k8s_version, "Wrong db version in {}".format(K8S_VALUES_FILE)
        )
        self.assertEqual(
            version, configmap_version, "Wrong db version in {}".format(CONFIGMAP_FILE)
        )

    def test_js_version(self):
        version = get_match_from_file(ENV_FILE, r"JS_VERSION=([0-9.]*)")
        k8s_version = get_match_from_file(K8S_VALUES_FILE, r"jsVersion: ([0-9.]*)")
        configmap_version = get_match_from_file(
            CONFIGMAP_FILE, r"\.Values\.jsVersion \| default \"([0-9.]*)\""
        )

        self.assertEqual(
            version, k8s_version, "Wrong js version in {}".format(K8S_VALUES_FILE)
        )
        self.assertEqual(
            version, configmap_version, "Wrong js version in {}".format(CONFIGMAP_FILE)
        )

    def test_system_version(self):
        version = get_match_from_file(ENV_FILE, r"SYSTEM_VERSION=([\-_a-zA-Z0-9.]*)")
        k8s_version = get_match_from_file(
            K8S_VALUES_FILE, r"systemVersion: ([\-_a-zA-Z0-9.]*)"
        )
        configmap_version = get_match_from_file(
            CONFIGMAP_FILE, r"\.Values\.systemVersion \| default \"([\-_a-zA-Z0-9.]*)\""
        )

        self.assertEqual(
            version, k8s_version, "Wrong system version in {}".format(K8S_VALUES_FILE)
        )
        self.assertEqual(
            version,
            configmap_version,
            "Wrong system version in {}".format(CONFIGMAP_FILE),
        )

    def test_deployment_version(self):
        version = get_match_from_file(
            COMPOSE_FILE, r"image: hasura/graphql-engine:([a-zA-Z0-9.\-_]*)"
        )
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("graphql"),
            r"image: hasura/graphql-engine:([a-zA-Z0-9.\-_]*)",
        )
        self.assertEqual(version, k8s_version)

        version = get_match_from_file(COMPOSE_FILE, r"image: nginx:([a-zA-Z0-9.\-_]*)")
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("nginx"), r"image: nginx:([a-zA-Z0-9.\-_]*)"
        )
        self.assertEqual(version, k8s_version)

        version = get_match_from_file(
            COMPOSE_FILE, r"image: rabbitmq:([a-zA-Z0-9.\-_]*)"
        )
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("rabbitmq"), r"image: rabbitmq:([a-zA-Z0-9.\-_]*)"
        )
        self.assertEqual(version, k8s_version)

        version = get_match_from_file(
            COMPOSE_FILE, r"image: timescale/timescaledb:([a-zA-Z0-9.\-_]*)"
        )
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("postgres"),
            r"image: timescale/timescaledb:([a-zA-Z0-9.\-_]*)",
        )
        self.assertEqual(version, k8s_version)

        version = get_match_from_file(
            COMPOSE_FILE, r"image: postgrest/postgrest:([a-zA-Z0-9.\-_]*)"
        )
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("postgrest"),
            r"image: postgrest/postgrest:([a-zA-Z0-9.\-_]*)",
        )
        self.assertEqual(version, k8s_version)

        version = get_match_from_file(
            COMPOSE_FILE, r"image: subzerocloud/pg-amqp-bridge:([a-zA-Z0-9.\-_]*)"
        )
        k8s_version = get_match_from_file(
            DEPLOYMENT_FILE.format("pg-amqp-bridge"),
            r"image: subzerocloud/pg-amqp-bridge:([a-zA-Z0-9.\-_]*)",
        )
        self.assertEqual(version, k8s_version)

    def test_env_values(self):
        env_vals = set(get_matches_from_file(ENV_FILE, r"([A-Z_]+)="))
        env_vals.remove("COMPOSE_PROJECT_NAME")
        dc_vals = set(get_matches_from_file(COMPOSE_FILE, r"\$\{([A-Z_]+)[:\-0-9]*\}"))

        self.assertTrue(dc_vals.issubset(env_vals))

        k8s_vals = set(get_matches_from_file(K8S_VALUES_FILE, r"([A-Za-z]+):"))
        env_vals = {k.lower().replace("_", "") for k in env_vals}
        env_vals.difference_update(
            {
                "jwtsecretkey",
                "flasksecretkey",
                "securitypasswordsalt",
                "hasurasecretkey",
                "artemiswebhost",
            }
        )
        k8s_vals = {k.lower() for k in k8s_vals}

        self.assertTrue(env_vals.issubset(k8s_vals))


if __name__ == "__main__":
    unittest.main()
