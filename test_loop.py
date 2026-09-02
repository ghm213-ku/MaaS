import asyncio
import time

async def _run_live_loop(duration_seconds: float, refresh_rate: int):
    _stop_event = asyncio.Event()
    
    end_time = asyncio.get_event_loop().time() + duration_seconds
    timeout = 1.0 / refresh_rate if refresh_rate > 0 else 0.04
    
    print(f"start: {asyncio.get_event_loop().time()}, end: {end_time}, timeout: {timeout}")
    count = 0
    while asyncio.get_event_loop().time() < end_time:
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=timeout)
            break
        except asyncio.TimeoutError as e:
            print(f"timeout {count} caught {type(e)}")
            pass
        except Exception as e:
            print(f"Other exception: {e} {type(e)}")
            break
            
        count += 1
        print(f"loop {count}")
    
    print(f"finished loop with count {count}")

asyncio.run(_run_live_loop(1.0, 10))
