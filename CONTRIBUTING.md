# Contributing to ARTEMIS

*First*: Feel free to ask, or submit the issue or
pull request anyway. We appreciate any contributions,
and we don't want a wall of rules to get in
the way of that.

However, for those individuals who want a bit more guidance on the best way to
contribute to the project, read on. This document will cover what we're looking
for. By addressing all the points we're looking for, the chances that we
can quickly merge or address your contributions will increase.

## Overview

[artemis](https://github.com/FORTH-ICS-INSPIRE/artemis) is a mono-repo
consisting of 3 components.

1. Back-End (Database, Microservices, Containers, etc)
2. Front-End (Flask, API, etc)
3. Build System

All of the three components have a single version, denoted by the git
tag.

## Issues

### Reporting an Issue

- Make sure you test against the latest released version. It is possible that we
  may have already fixed the bug you're experiencing.

- Provide steps and data to reproduce the issue.

- Please include ARTEMIS logs, if relevant.

- Please include appropriate issue labels, if relevant.

## Common guidelines

- Please make sure there is an issue associated with the work that you're doing.

- If you're working on an issue, please comment that you are doing so to prevent
  duplicate work by others also.

- Use pre-commit hooks by installing pre-commit and adding the hooks to the repository.
  This will run all the necessary tests before pushing your code.

```
pip install pre-commit
pre-commit install
```

- Squash your commits and refer to the issue using `fix #<issue-no>` or `close
  #<issue-no>` in the commit message, at the end.
  For example: `resolve answers to everything (fix #42)` or `resolve answers to everything, fix #42`

- Rebase master with your branch before submitting a pull request.

- For a PR template, please check [this file](docs/pull_request_template.md).

## Extensions

### Implementing additional Monitors (taps)

Take a look at [this script](backend/core/taps/exabgp_client.py)
which implements the exaBGP BGP update publisher, or
[this script](backend/core/taps/ripe_ris.py) which implements the
RIPE RIS BGP update publisher.

### Adding custom (containerized) micro-services

- Usage of character '\_' on micro-service names is prohibited.
- For more information contact the ARTEMIS team (details in the [README](README.md)).

(Credits: Some of the content of this file is adapted from [here](https://raw.githubusercontent.com/hasura/graphql-engine/master/CONTRIBUTING.md).)
