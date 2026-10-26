from factory.queue import Worker

if __name__ == "__main__":
    worker = Worker()
    try:
        worker.loop()
    except KeyboardInterrupt:
        worker.close()
