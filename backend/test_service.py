from collector.db.loader import DataLoader
from core.service.screener_service import ScreenerService
from core.api.models.schemas import ScreenerRequest

loader = DataLoader().load()
service = ScreenerService(loader)

# Test 1: Sort by change_pct desc
req = ScreenerRequest(page=1, page_size=3, sort_by='change_pct', sort_order='desc')
resp = service.screen_stocks(req)
print('Test 1 - Sort by change_pct desc: total=%d, count=%d' % (resp.total, len(resp.data)))
for s in resp.data:
    print('  %s %s listed=%s close=%s change_pct=%s' % (s.stock_code, s.stock_name, s.listed_board.value, s.close, s.change_pct))

# Test 2: Filter meta
print()
print('Test 2 - Filter meta:')
meta = service.get_filter_meta()
for g in meta:
    print('  Group: %s (%s) fields=%d' % (g.id, g.label, len(g.fields)))

# Test 3: Sort by volume desc
req2 = ScreenerRequest(page=1, page_size=3, sort_by='volume', sort_order='desc')
resp2 = service.screen_stocks(req2)
print()
print('Test 3 - Sort by volume desc: total=%d' % resp2.total)
for s in resp2.data:
    print('  %s %s volume=%s' % (s.stock_code, s.stock_name, s.volume))

# Test 4: Sort by market_cap desc
req3 = ScreenerRequest(page=1, page_size=3, sort_by='market_cap', sort_order='desc')
resp3 = service.screen_stocks(req3)
print()
print('Test 4 - Sort by market_cap desc: total=%d' % resp3.total)
for s in resp3.data:
    print('  %s %s market_cap=%s' % (s.stock_code, s.stock_name, s.market_cap))