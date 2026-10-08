# ConsolePi+ 1.9.1 – vzdálený syslog

Nastavení je v **Systém → Logování → Vzdálený syslog**. Výchozí stav je vypnuto.
Zadejte server (DNS jméno nebo IPv4/IPv6), port, transport a severity. Doporučený
transport je **TCP/TLS**, běžně port **6514**. Nešifrované TCP je volitelné pro
prostředí, která jej výslovně požadují; UDP není podporované.

## Severity podle vzoru síťových prvků

Vybraný práh zahrnuje všechny závažnější zprávy: **Warning (4) = 0–4**,
**Informational (6) = 0–6**. Výchozí hodnota 6 zahrnuje běžné konzolové relace.

| Číslo | Úroveň | Význam |
| --- | --- | --- |
| 0 | Emergency | Celková nefunkčnost |
| 1 | Alert | Okamžitý zásah |
| 2 | Critical | Kritická porucha |
| 3 | Error | Chyba operace nebo služby |
| 4 | Warning | Varování, neúspěšná autentizace |
| 5 | Notice | Významná změna konfigurace |
| 6 | Informational | Běžné přístupy a konzolové relace |
| 7 | Debug | Diagnostické události povolených zdrojů |

Práh filtruje již existující události; nezapíná další diagnostiku a nevytváří
událost pro každou operaci, která vlastní auditní záznam dosud nemá.

## Odesílané zdroje

- Tag `consolepi`: otevření/ukončení a odmítnutí konzolové relace, změny
  allowlistu a další operace, které ConsolePi+ už zaznamenává přes logger.
- `sshd` / `sshd-session`: SSH autentizace. Vybrané zprávy o neúspěšné
  autentizaci jsou pro vzdálený přenos povýšeny z info na Warning (4).
- `consolepi-web-audit`: úspěšné přihlášení (6) a neúspěšné přihlášení (4),
  pouze výsledek a adresa klienta, bez hesla a obsahu formuláře.
- Kernel: pouze události s označením `nft-input-drop`.
- systemd: pouze chyby 0–4 týkající se consolepi-web, consolepi-port-monitor,
  nginx, ssh nebo nftables.

Sériové přepisy ani soubory `/var/log/consolepi/transcripts` se nečtou a
neodesílají. Povolené události však obsahují provozní metadata (IP, účet, port,
identifikaci zařízení); přístup a retenci na serveru nastavte podle potřeb organizace.

## TLS a důvěra

TLS ověřuje certifikát i DNS jméno/IP serveru. Prázdné pole CA používá systémové
CA. Pro interní PKI vložte veřejný PEM certifikát CA; privátní klíč se nevkládá.
Server musí přijímat RFC 5424 zprávy s RFC 5425 octet-counting framingem. Stejné
rámování používá i varianta prostého TCP. Klientský certifikát/mTLS tato verze
nenabízí. Chyba ověření TLS nikdy nepřepne přenos automaticky na nešifrovaný.

## Fronta a stav

Samostatná služba `consolepi-syslog.service` čte vybrané události z journalu.
SQLite fronta v `/var/lib/consolepi-syslog` je přístupná pouze root a zachovává
čekající zprávy při restartu služby. Uchovává nejvýše **2 000 zpráv**, text jedné
události je omezen na 2 048 znaků. Při zaplnění zahodí nejstarší zprávu a zvýší
počitadlo; žádný syslog server proto není zárukou bezeztrátového auditu.

Výpadek cíle způsobí opakování po 10 sekundách. Konzolové relace síťového
odesílatele nečekají. Web ukazuje stav služby, čekající/zahozené zprávy, poslední
chybu a čas předání zprávy do spojení. TCP/TLS samo nepotvrzuje trvalé uložení
na serveru; po nejistém přerušení se mohou objevit duplicity nebo ztráta.

**Uložení konfigurace nebo vypnutí vyprázdní frontu**, včetně změny severity.
Tím se zabrání odeslání původních událostí na nově zvolený cíl. Zálohuje se pouze
konfigurace, nikoli fronta. Tovární reset a sanitizace generic image odstraní
server, vlastní CA a čekající události; generic validátor kontroluje vypnutí.

## Ověření

1. Uložte zapnuté nastavení s odpovídající CA a portem.
2. Klikněte na **Odeslat testovací zprávu**. `SYSLOG_TEST version=1.9.1` používá
   právě nastavenou severity, aby test prošel filtrem.
3. Ověřte přijetí na serveru. Zpráva webu potvrzuje lokální zapsání události,
   nikoli vzdálené uložení.
4. Vyzkoušejte práh 4 a 6, nesprávný certifikát, výpadek a obnovení serveru.
5. Sledujte frontu a ověřte, že relace přes porty 2201–2204 zůstávají funkční.

Diagnostika na zařízení:

```sh
sudo consolepi-control syslog status
sudo systemctl status consolepi-syslog --no-pager
sudo journalctl -u consolepi-syslog -n 50 --no-pager
```

## Distribuce

Syslog je rozšíření zdrojů 1.9.1. Původní image a archivy vydané 2. 10. 2026
jej neobsahují. Aktualizované distribuční soubory lze označit za ověřené až po
instalaci a testu na RPi; změna zdrojů sama již zapsanou SD kartu neaktualizuje.
