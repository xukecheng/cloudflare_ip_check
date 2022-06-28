# -*- coding: utf8 -*-
import logging
import csv
import sys
import os
import requests
import json
import CloudFlare
import subprocess


# 日志配置
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)

# 环境变量获取
work_dir = os.getenv("WORKDIR", "./")
dns_names = os.getenv("DNSNAMES", "test.domain.com test1.domain.com")
token = os.getenv("TOKEN", "xxxxxxxx")


def main_handler(event, context):
    subprocess.run(["./CloudflareST", "-o", f"{work_dir}result.csv"])

    csv_read = csv.reader(open(f"{work_dir}result.csv"))

    index = 0
    for i in csv_read:
        if index == 1:
            ip_address = i[0]
            break
        index += 1
    print(ip_address)

    # ip_address = "172.67.138.237"

    logger.info("需要更新的域名：" + dns_names)

    dns_names_list = dns_names.split(" ")
    print(dns_names_list)

    for dns_name in dns_names_list:
        update_dns_record(dns_name=dns_name, ip_address=ip_address)

    return "Done"


def clear_files(src):
    try:
        logger.info("clear work dir...")
        if os.path.isfile(src):
            os.remove(src)
        elif os.path.isdir(src):
            for item in os.listdir(src):
                itemsrc = os.path.join(src, item)
                clear_files(itemsrc)
    except Exception as err:
        logging.exception(err)
        pass


def update_dns_record(dns_name, ip_address, ip_address_type="A"):
    host_name, zone_name = ".".join(dns_name.split(".")[:2]), ".".join(
        dns_name.split(".")[-2:]
    )

    print("MY IP: %s %s" % (dns_name, ip_address))

    cf = CloudFlare.CloudFlare(token=token)

    # grab the zone identifier
    try:
        params = {"name": zone_name}
        zones = cf.zones.get(params=params)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit("/zones %d %s - api call failed" % (e, e))
    except Exception as e:
        exit("/zones.get - %s - api call failed" % (e))

    if len(zones) == 0:
        exit("/zones.get - %s - zone not found" % (zone_name))

    if len(zones) != 1:
        exit("/zones.get - %s - api call returned %d items" % (zone_name, len(zones)))

    zone = zones[0]

    zone_name = zone["name"]
    zone_id = zone["id"]

    do_dns_update(cf, zone_name, zone_id, dns_name, ip_address, ip_address_type)


def do_dns_update(cf, zone_name, zone_id, dns_name, ip_address, ip_address_type):
    """Cloudflare API code - example"""

    try:
        params = {"name": dns_name, "match": "all", "type": ip_address_type}
        dns_records = cf.zones.dns_records.get(zone_id, params=params)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit("/zones/dns_records %s - %d %s - api call failed" % (dns_name, e, e))

    updated = False

    # update the record - unless it's already correct
    for dns_record in dns_records:
        old_ip_address = dns_record["content"]
        old_ip_address_type = dns_record["type"]

        if ip_address_type not in ["A", "AAAA"]:
            # we only deal with A / AAAA records
            continue

        if ip_address_type != old_ip_address_type:
            # only update the correct address type (A or AAAA)
            # we don't see this becuase of the search params above
            print("IGNORED: %s %s ; wrong address family" % (dns_name, old_ip_address))
            continue

        if ip_address == old_ip_address:
            print("UNCHANGED: %s %s" % (dns_name, ip_address))
            updated = True
            continue

        proxied_state = dns_record["proxied"]

        # Yes, we need to update this record - we know it's the same address type

        dns_record_id = dns_record["id"]
        dns_record = {
            "name": dns_name,
            "type": ip_address_type,
            "content": ip_address,
            "proxied": proxied_state,
        }
        try:
            dns_record = cf.zones.dns_records.put(
                zone_id, dns_record_id, data=dns_record
            )
        except CloudFlare.exceptions.CloudFlareAPIError as e:
            exit(
                "/zones.dns_records.put %s - %d %s - api call failed" % (dns_name, e, e)
            )
        print("UPDATED: %s %s -> %s" % (dns_name, old_ip_address, ip_address))
        updated = True

    if updated:
        return

    # no exsiting dns record to update - so create dns record
    dns_record = {"name": dns_name, "type": ip_address_type, "content": ip_address}
    try:
        dns_record = cf.zones.dns_records.post(zone_id, data=dns_record)
    except CloudFlare.exceptions.CloudFlareAPIError as e:
        exit("/zones.dns_records.post %s - %d %s - api call failed" % (dns_name, e, e))
    print("CREATED: %s %s" % (dns_name, ip_address))


if __name__ == "__main__":
    main_handler({}, {})
