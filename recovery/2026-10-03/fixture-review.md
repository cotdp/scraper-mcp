# Synthetic fixture scan review

The default Gitleaks scan flagged generic API-key patterns in tests/test_admin_config.py. The values were verified as synthetic. Deckzy CI comments describe deliberately inert settings, with example-domain and CI markers. Scraper masking unit tests use literal placeholder markers and sequential digits without making network requests.

The full original bytes are preserved. A scanner allowlist matches only these exact fixture lines in their exact snapshot paths; all default secret rules remain enabled.
