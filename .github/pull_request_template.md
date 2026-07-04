## What does this PR do?

<!-- Briefly describe the change and why it's needed -->

## Related issue / discussion

<!-- Link an issue, or the LinkedIn/discussion thread this came from, if any -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Security fix
- [ ] Refactor / code health
- [ ] Docs / config only

## Checklist

- [ ] I ran `python -m pytest tests/ -v` locally and all tests pass
- [ ] I added/updated tests for the behavior I changed
- [ ] I did not commit anything under `uploads/`, `.env`, or `__pycache__/`
- [ ] If this touches the PIN, download, or rate-limiting logic, I manually
      re-verified the one-time-download flow still works (upload → PIN →
      download → confirm the link 404s on reuse)

## Screenshots (if UI changed)

<!-- Drag and drop images here -->
