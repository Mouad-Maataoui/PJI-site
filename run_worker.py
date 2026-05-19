"""
Script pour lancer le worker Celery et/ou le scheduler Beat
"""
import argparse
import subprocess
import sys
import os



def run_worker(loglevel="INFO", concurrency=4, queues="main-queue,low-queue"):
    """Lance un worker Celery"""
    cmd = [
        "celery",
        "-A", "app.worker.celery_app",
        "worker",
        f"--loglevel={loglevel}",
        f"--concurrency={concurrency}",
        f"--queues={queues}"
    ]
    if logfile:
        with open(logfile, "a", buffering=1) as f:
            subprocess.run(cmd, stdout=f, stderr=f)
    else:
        subprocess.run(cmd)


def run_beat(loglevel="INFO"):
    """Lance le scheduler Celery Beat"""
    cmd = [
        "celery",
        "-A", "app.worker.celery_app",
        "beat",
        f"--loglevel={loglevel}"
    ]
    if logfile:
        with open(logfile, "a", buffering=1) as f:
            subprocess.run(cmd, stdout=f, stderr=f)
    else:
        subprocess.run(cmd)


def run_flower(port=5555, loglevel="INFO"):
    """Lance Flower pour monitorer Celery"""
    cmd = [
        "celery",
        "-A", "app.worker.celery_app",
        "flower",
        f"--port={port}",
        f"--loglevel={loglevel}"
    ]
    if logfile:
        with open(logfile, "a", buffering=1) as f:
            subprocess.run(cmd, stdout=f, stderr=f)
    else:
        subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lanceur pour Celery")
    parser.add_argument(
        "command",
        choices=["worker", "beat", "flower", "all"],
        help="Commande à exécuter"
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Nombre de workers concurrents"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="Port pour Flower"
    )
    parser.add_argument(
        "--logtype",
        default="stdout",
        help="Niveau de log (stdout, file=filepath)"
    )
    
    args = parser.parse_args()

    logfile = None
    if "file=" in args.logtype:
        logfile = args.logtype.split('=')[1]
    
    if args.command == "worker":
        run_worker(args.loglevel, args.concurrency)
    elif args.command == "beat":
        run_beat(args.loglevel)
    elif args.command == "flower":
        run_flower(args.port, args.loglevel)
    elif args.command == "all":
        import multiprocessing
        
        processes = []
        
        worker_process = multiprocessing.Process(
            target=run_worker,
            args=(args.loglevel, args.concurrency)
        )
        worker_process.start()
        processes.append(worker_process)
        
        beat_process = multiprocessing.Process(
            target=run_beat,
            args=(args.loglevel,)
        )
        beat_process.start()
        processes.append(beat_process)
        
        flower_process = multiprocessing.Process(
            target=run_flower,
            args=(args.port, args.loglevel)
        )
        flower_process.start()
        processes.append(flower_process)
        
        # Attendre que tous les processus terminent
        for process in processes:
            process.join()