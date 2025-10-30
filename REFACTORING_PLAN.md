# Scraper MCP Refactoring Plan

## Current State Analysis

### File Size Breakdown
- **Total**: 2,051 lines in `server.py` (64% of entire codebase)
- **Dashboard HTML/CSS**: 1,015 lines (49.5%) - embedded in Python
- **Scraping Business Logic**: 499 lines (24.3%)
- **MCP Tools**: 143 lines (7.0%)
- **Admin API**: 138 lines (6.7%)
- **Provider Management**: 129 lines (6.3%)
- **Response Models**: 55 lines (2.7%)
- **Imports/Config**: 100 lines (4.9%)

### Issues Identified

1. **❌ Single Responsibility Principle Violation**
   - One file handles: MCP tools, admin API, dashboard, business logic, config
   - Impossible to work on one concern without seeing all others

2. **❌ Embedded UI Anti-pattern**
   - 1,015 lines of HTML/CSS/JavaScript in Python strings
   - No syntax highlighting, hard to maintain
   - Can't use proper frontend tooling

3. **❌ Mixed Concerns**
   - Business logic (scraping) mixed with routing
   - Configuration management scattered throughout
   - No clear service layer

4. **❌ Testing Difficulties**
   - Can't test scraping logic without loading entire server
   - Dashboard can't be tested independently
   - Admin API tightly coupled to MCP tools

5. **❌ Poor Maintainability**
   - Hard to navigate 2,000+ line file
   - Difficult to find specific functionality
   - Risky to modify (high chance of breaking unrelated code)

---

## Refactoring Options

### Option 1: Minimal Split (Quick Win)
**Effort**: 2-3 hours | **Risk**: Low | **Benefit**: Medium

Extract the most obvious pain points with minimal changes:

```
src/scraper_mcp/
├── __init__.py
├── __main__.py
├── server.py                  # MCP tools + core server (500 lines)
├── admin/
│   ├── __init__.py
│   └── routes.py             # Admin API endpoints (150 lines)
├── dashboard/
│   ├── __init__.py
│   ├── routes.py             # Dashboard route (50 lines)
│   └── templates/
│       └── dashboard.html    # HTML/CSS/JS (1000 lines)
├── services.py               # Business logic functions (500 lines)
├── models.py                 # Pydantic schemas (100 lines)
└── [existing files...]
```

**Pros:**
- ✅ Quick to implement
- ✅ Removes ~75% of lines from server.py
- ✅ Dashboard now editable with proper tooling
- ✅ Low risk of breaking changes

**Cons:**
- ⚠️ Still monolithic scraping logic
- ⚠️ MCP tools and server still coupled
- ⚠️ Doesn't follow best practices fully

---

### Option 2: Domain-Based Split (Recommended) ⭐
**Effort**: 4-6 hours | **Risk**: Medium | **Benefit**: High

Split by domain/feature following FastAPI/FastMCP best practices:

```
src/scraper_mcp/
├── __init__.py
├── __main__.py
├── core/
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── dependencies.py      # Shared dependencies
│   └── server.py            # FastMCP initialization (50 lines)
├── models/
│   ├── __init__.py
│   ├── scrape.py            # ScrapeResponse, BatchScrapeResponse
│   └── links.py             # LinksResponse, BatchLinksResponse
├── tools/
│   ├── __init__.py
│   ├── router.py            # MCP tool registrations (150 lines)
│   └── service.py           # Scraping business logic (500 lines)
├── admin/
│   ├── __init__.py
│   ├── router.py            # Admin API routes (150 lines)
│   └── service.py           # Admin logic (cache, config, stats)
├── dashboard/
│   ├── __init__.py
│   ├── router.py            # Dashboard route (50 lines)
│   └── templates/
│       ├── dashboard.html   # Main dashboard HTML
│       ├── styles.css       # Extracted CSS
│       └── scripts.js       # Extracted JavaScript
└── [existing files...]
```

**Pros:**
- ✅ Clean separation of concerns
- ✅ Each domain can be developed independently
- ✅ Easy to test individual components
- ✅ Follows FastAPI best practices
- ✅ Dashboard uses proper template system
- ✅ Clear service layer

**Cons:**
- ⚠️ Requires more upfront work
- ⚠️ Need to update imports in tests

---

### Option 3: Full Package-Oriented (Enterprise)
**Effort**: 8-12 hours | **Risk**: High | **Benefit**: Very High

Complete enterprise-grade structure with full separation:

```
src/scraper_mcp/
├── __init__.py
├── __main__.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── dependencies.py
│   ├── exceptions.py
│   └── server.py
├── models/
│   ├── __init__.py
│   ├── scrape.py
│   ├── links.py
│   └── api.py               # Admin API schemas
├── tools/
│   ├── __init__.py
│   ├── router.py            # Tool registrations
│   ├── service.py           # Orchestration layer
│   ├── scraping/
│   │   ├── __init__.py
│   │   ├── html.py          # HTML scraping
│   │   ├── markdown.py      # Markdown conversion
│   │   ├── text.py          # Text extraction
│   │   └── links.py         # Link extraction
│   └── batch.py             # Batch processing logic
├── admin/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py
│   └── schemas.py           # Admin-specific schemas
├── dashboard/
│   ├── __init__.py
│   ├── router.py
│   ├── service.py           # Dashboard data aggregation
│   ├── templates/
│   │   └── dashboard.html
│   ├── static/
│   │   ├── css/
│   │   │   └── dashboard.css
│   │   └── js/
│   │       └── dashboard.js
└── [existing files...]
```

**Pros:**
- ✅ Fully scalable architecture
- ✅ Maximum separation of concerns
- ✅ Static assets properly managed
- ✅ Easy to add new features
- ✅ Enterprise-ready

**Cons:**
- ❌ Significant upfront investment
- ❌ Possibly overkill for current project size
- ❌ Requires extensive test updates

---

## Recommendation: Option 2 (Domain-Based Split) ⭐

**Why Option 2 is best:**

1. **Right-sized for project** - Not too simple, not over-engineered
2. **Best practices** - Follows FastAPI/FastMCP recommendations
3. **Maintainable** - Clear domain boundaries
4. **Testable** - Easy to unit test each component
5. **Extensible** - Easy to add new tools or admin features
6. **Reasonable effort** - 4-6 hours vs 8-12 for Option 3

**Implementation Priority:**

1. ✅ Extract dashboard HTML to templates (biggest win)
2. ✅ Create domain packages (tools/, admin/, dashboard/, core/)
3. ✅ Move business logic to service modules
4. ✅ Create router modules for each domain
5. ✅ Update server.py to orchestrate routers
6. ✅ Update tests to import from new structure

---

## Migration Strategy

### Phase 1: Create Structure (30 min)
- Create new directory structure
- Add `__init__.py` files
- Create empty router/service files

### Phase 2: Extract Dashboard (45 min)
- Move HTML to `dashboard/templates/dashboard.html`
- Split CSS/JS into separate sections
- Create dashboard router
- Test dashboard loads correctly

### Phase 3: Extract Admin (60 min)
- Move admin routes to `admin/router.py`
- Move admin logic to `admin/service.py`
- Update imports
- Test admin API endpoints

### Phase 4: Extract Tools (90 min)
- Move MCP tools to `tools/router.py`
- Move business logic to `tools/service.py`
- Move models to `models/`
- Update imports

### Phase 5: Create Core (30 min)
- Move config to `core/config.py`
- Create minimal `core/server.py`
- Update `__main__.py`

### Phase 6: Testing & Validation (60 min)
- Run all tests
- Fix import issues
- Verify all functionality works
- Update documentation

**Total Estimated Time**: 5-6 hours

---

## Success Metrics

- ✅ `server.py` reduced from 2,051 to <200 lines
- ✅ All tests passing
- ✅ Dashboard still functional
- ✅ Admin API still functional
- ✅ MCP tools still functional
- ✅ Easier to navigate codebase
- ✅ Can modify one domain without touching others
