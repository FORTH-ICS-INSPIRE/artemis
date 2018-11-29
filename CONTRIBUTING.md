# Contributing to ARTEMIS

*First*: if you're unsure or afraid of anything, just ask, or submit the issue or
pull request anyway. You won't be yelled at for giving your best effort. The
worst that can happen is that you'll be politely asked to change something. We
appreciate any contributions, and we don't want a wall of rules to get in
the way of that.

However, for those individuals who want a bit more guidance on the best way to
contribute to the project, read on. This document will cover what we're looking
for. By addressing all the points we're looking for, the chances that we
can quickly merge or address your contributions will increase.

## Overview

[artemis](https://github.com/FORTH-ICS-INSPIRE/artemis-tool) is a mono-repo
consisting of 3 components.

1. Root container composition
2. Frontend
3. Backend

All of the three components have a single version, denoted by the git
tag.

### Docs

Contributing guide for docs can be found at TBD.

## Issues

### Reporting an Issue

- Make sure you test against the latest released version. It is possible that we
  may have already fixed the bug you're experiencing.

- Provide steps and data to reproduce the issue.

- Please include logs of the server, if relevant.

## Common guidelines

- Please make sure there is an issue associated with the work that you're doing.

- If you're working on an issue, please comment that you are doing so to prevent
  duplicate work by others also.

- Squash your commits and refer to the issue using `fix #<issue-no>` or `close
  #<issue-no>` in the commit message, at the end.
  For example: `resolve answers to everything (fix #42)` or `resolve answers to everything, fix #42`

- Rebase master with your branch before submitting a pull request.

(Credits: Most of the content of this file is adapted from https://raw.githubusercontent.com/hasura/graphql-engine/master/CONTRIBUTING.md)
