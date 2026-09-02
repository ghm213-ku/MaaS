import asyncio
from unittest.mock import MagicMock
from app.services.time_histograms_live import StartStopLiveMeasurementHandler, HistogramLiveMeasurementHandler, CorrelationLiveMeasurementHandler
from app.models import StartStopLiveMetadata, HistogramLiveMetadata, CorrelationLiveMetadata
from Swabian import TimeTagger

async def main():
    tagger = TimeTagger.createTimeTagger()
    handler = StartStopLiveMeasurementHandler(tagger=tagger)
    handler.status_id = "test_status"
    handler.redis_client = MagicMock()
    
    metadata = StartStopLiveMetadata(
        click_channel=1,
        start_channel=2,
        binwidth=1000,
        n_bins=1000,
        refresh_rate=10
    )
    
    print("Testing StartStopLive...")
    task = asyncio.create_task(handler.start(0.5, metadata))
    await asyncio.sleep(0.6)
    
    print(f"Redis publish calls: {handler.redis_client.publish.call_count}")
    
    # Check payload of last call
    if handler.redis_client.publish.call_count > 0:
        args, kwargs = handler.redis_client.publish.call_args
        print(f"Last payload starts with: {args[1][:100]}")
        
    tagger.freeTimeTagger()

if __name__ == "__main__":
    asyncio.run(main())
