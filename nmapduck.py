import sqlite3
from sqlite3 import Error
import ipaddress
import subprocess
from threading import Thread
from threading import Lock
from threading import Event
from time import sleep
import random
from os import path


MAX_WORKERS = 5
DB_FILE = "/home/debian/brute/nmap.db/db.sqlite"
OUT_DIR = "/home/debian/brute/nmap.db/out"
BASE_DIR = "/home/debian/brute/nmap.db/in"

NMAP_CMD_BASE = "nmap -vv -n -sV --open -p22,2222,23 -4"

workers_lock = Lock()
workers_active = 0
workers_pool = list()
workers_kill = Event()


def ip_range_list(start_ip, end_ip):
    start = list(map(int, start_ip.split(".")))
    end = list(map(int, end_ip.split(".")))

    temp = start
    ip_range = list()

    ip_range.append(start_ip)
    while temp != end:
        start[3] += 1
        for i in (3, 2, 1):
            if temp[i] == 256:
                temp[i] = 0
                temp[i - 1] += 1
            ip_range.append(".".join(map(str, temp)))

    return ip_range


def out_xml_file_path(start_ip, end_ip):
    return path.join(OUT_DIR, start_ip + "-" + end_ip) + ".xml"


def ip_range_file_path(start_ip, end_ip):
    return path.join(BASE_DIR, start_ip + "-" + end_ip) + ".list"


def ip_range_file(start_ip, end_ip):
    ip_range = ip_range_list(start_ip, end_ip)
    random.shuffle(ip_range)
    f = open(ip_range_file_path(start_ip, end_ip), "w")
    for ip in ip_range:
        f.write(ip + "\n")
    f.close()


def create_connection(db_file=DB_FILE):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)

    return conn

def work_count():
    conn = create_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(ip_start) FROM ranges WHERE status = 0")
    cnt = cur.fetchone()[0]
    cur.close()
    conn.close()
    return cnt


def workers_count():
    conn = create_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(ip_start) FROM ranges WHERE status = 1")
    cnt = cur.fetchone()[0]
    cur.close()
    conn.close()
    return cnt


def update_worker_status(start_ip, end_ip, s):
    conn = create_connection()
    cur = conn.cursor()
    q = "UPDATE ranges SET status=" + str(s) + " WHERE (ip_start=" + str(start_ip) + ")AND(ip_end=" + str(
        end_ip) + ")"
    cur.execute(q)
    cur.close()
    conn.close()

def update_worker_scan(start_ip, end_ip):
    conn = create_connection()
    cur = conn.cursor()
    q = "UPDATE ranges SET status=" + str(s) + " WHERE (ip_start=" + str(start_ip) + ")AND(ip_end=" + str(
        end_ip) + ")"
    cur.execute(q)
    row = cur.fetchone()
    if row is None:
        return



def worker(start_ip, end_ip):
    global workers_active

    with workers_lock:
        workers_active += 1
        print(str(start_ip) + "-" + str(end_ip) + ":" + "INC(workers):" + str(workers_active))

    update_worker_status(1, start_ip, end_ip)

    ip_start = str(ipaddress.IPv4Address(start_ip))
    ip_end = str(ipaddress.IPv4Address(end_ip))
    ip_range = ip_start + "-" + ip_end
    ip_range_file(ip_start, ip_end)

    cmd = NMAP_CMD_BASE + " -iL " + ip_range_file_path(ip_start, ip_end) + " -oX " + out_xml_file_path(ip_start, ip_end)

    print(cmd)
    print(str(start_ip) + "-" + str(end_ip) + ":" + "SUB(nmap)")
    p_nmap = subprocess.Popen(['bash', '-c', cmd], subprocess.PIPE, stderr=subprocess.STDOUT)
    while not workers_kill.wait(1):
        nmap_res = p_nmap.poll()
        if nmap_res is not None:
            print(str(start_ip) + "-" + str(end_ip) + ":" + "RES(nmap):" + str(nmap_res));
            break;
    if p_nmap.poll() is None:
        print(str(start_ip) + "-" + str(end_ip) + ":" + "KILL(nmap):" + str(nmap_res));
        p_nmap.kill()
    else:
        print(str(start_ip) + "-" + str(end_ip) + ":" + "RES(nmap):" + str(nmap_res));

    update_worker_status(2, start_ip, end_ip)

    with workers_lock:
        workers_active -= 1
        print(str(start_ip) + "-" + str(end_ip) + ":" + "DEC(workers):" + str(workers_active))


def add_workers(cnt):
    global workers_active

    conn = create_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT ip_start, ip_end, cc, region, city FROM ranges WHERE status = 0 ORDER BY RANDOM() LIMIT " + str(
            cnt))
    rows = cur.fetchall()
    for row in rows:
        print(row)

        start_ip = int(row[0])
        end_ip = int(row[1])

        print(str(row[0]) + str(row[1]) + ":START")
        thread = Thread(target=worker, args=(start_ip, end_ip))
        thread.start()

        print(str(row[0]) + str(row[1]) + ":WORKERS:" + str(workers_active))

    cur.close()
    conn.close()


def run_work():
    global workers_active

    cnt_work = work_count()
    while cnt_work > 0 and not workers_kill.wait(1):
        if workers_active < MAX_WORKERS:
            if cnt_work > MAX_WORKERS:
                print("Add workers to max: " + str(MAX_WORKERS - workers_active) + "\n")
                add_workers(MAX_WORKERS - workers_active)
            else:
                print("Add workers to count: " + str(cnt_work - workers_active) + "\n")
                add_workers(cnt_work - workers_active)

    sleep(1)


# select_ranges(conn)
worker_manager = Thread(target=run_work)
worker_manager.start()

while True:
    inp = input("Type your command:")
    if inp.lower() == "help":
        print("Helpanet! HELP | QUIT | PAUSE | WORKERS | STATUS")
    if inp.lower() == "quit":
        workers_kill.set()
        sleep(60)
        exit(1)
