import asyncio,sys
from tradertim_gateway.service import TraderTimService
from tradertim_gateway.models import Mode
svc=TraderTimService()
cmd=(sys.argv[1] if len(sys.argv)>1 else "status").lower()
if cmd=="status": print(asyncio.run(svc.status()))
elif cmd=="shadow": print(svc.operator_set_mode(Mode.SHADOW))
elif cmd=="live": print(svc.operator_set_mode(Mode.LIVE_POC))
elif cmd=="halt": print(svc.operator_set_mode(Mode.HALTED))
else: raise SystemExit("Use status|shadow|live|halt")
