import sys
import traceback

try:
    from Swabian import TimeTagger
    tagger = TimeTagger.createTimeTaggerVirtual()
    try:
        tagger.setInputDelay("1", 1000)
        print("Success with str, int")
    except Exception as e:
        print(f"Failed with str, int: {e}")

except Exception as e:
    print(f"Could not import or use TimeTagger: {e}")
