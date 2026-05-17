import traceback
try:
    import app
    print("OK")
except Exception as e:
    traceback.print_exc()