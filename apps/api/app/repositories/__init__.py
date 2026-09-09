"""Data-access layer — one repository per aggregate root, no business logic here.

Populated starting Phase 3. Routes never query the ORM directly; they go
through a service, which goes through a repository (see docs/domain-model.md).
"""
