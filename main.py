from cloudflare import main as cf_main
from namecom import main as namecom_main
from namecheap import main as namecheap_main
from dynadot import main as dynadot_main
from clear import clear_expired_domains

def main():
    namecheap_main()
    namecom_main()
    cf_main()
    dynadot_main()
    clear_expired_domains()

if __name__ == '__main__':
    main()
