# ConsolePi+ 1.9.1 – podklady pro bezpečnostní posouzení

Aktualizováno 8. 10. 2026. Dokumenty popisují vydání 1.9.1 a obsahují skutečné
výřezy z webu testovacího Raspberry Pi 3 B+. Ukazují příklad nastavení zařízení
192.168.100.124; nejde o doporučenou adresu ani důkaz vynucení bezpečnostních pravidel.

- [Bezpečnostní přehled pro auditora (DOCX)](01_Bezpecnostni_prehled_pro_auditora_se_screenshoty.docx)
- [Technická bezpečnostní dokumentace (DOCX)](02_Technicka_bezpecnostni_dokumentace_se_screenshoty.docx)
- [Akceptační testy a obrazové reference (XLSX)](03_Akceptacni_testy_se_screenshoty.xlsx)

Obrázky S01–S16 z 6. 10. 2026 jsou propojené s listem **Reference** v sešitu.
Obrázek S17 je lokální náhled nového panelu syslogu z 8. 10. 2026, nikoli snímek
nasazené funkce na RPi. Všech 22 testů je nadále **Nevyhodnoceno**; souhrnné vzorce,
výběr výsledků a barevné označení akceptace zahrnují také nové testy.
Screenshoty neověřují například nftables, oprávnění souborů, TLS protokoly,
zamítnutí podvrženého balíčku ani přístup z nepovolené sítě. Při pořízení nebyla
spuštěna obnova, záloha, změna hesla nebo instalace aktualizací.

## Vzdálený syslog ve zdrojovém rozšíření 1.9.1

Oba dokumenty obsahují kapitolu s nastavením severity 0–7, ověřováním certifikátu
a identity TLS serveru, rozsahem přenášených událostí a ochranou provozních metadat.
Popisují také omezenou frontu, ztráty a duplicity, vyprázdnění při uložení
konfigurace, zálohu, obnovu a reset. Sériové přepisy se do syslogu neodesílají.

Testy **11–22** ověřují výchozí vypnutí, hranice severity, povolené zdroje,
TLS, rámování a testovací zprávu, výpadek a restart, limit a oprávnění fronty,
změnu cíle a vypnutí, ochranu webového nastavení, reset a sanitizaci, obnovu
a identifikaci skutečně nasazeného rozšíření. Obsahují postup, očekávaný výsledek
a prázdné místo pro důkaz z RPi a přijímajícího serveru.

Místně prošlo 14 kontrol backendu a 6 kontrol webu. Tyto kontroly ani náhled
neuzavírají akceptaci instalace. Původní image a archivy vydané 2. 10. 2026 syslog
neobsahují; samotná hodnota `VERSION=1.9.1` proto nerozlišuje nasazení rozšíření.
Podrobnosti: [specifikace syslogu](../SYSLOG.md) a
[implementace a stav ověření v PR 22](https://github.com/jiriflos-eng/ConsolePi-Plus/pull/22).

## Upřesnění logování podle zdrojů 1.9.1

Přiložené dokumenty označují rozpor mezi původním tvrzením o nezaznamenávání
vstupu a popiskem webu „Úplný obousměrný přepis“. Následná kontrola zdrojového
kódu vydání tento rozdíl upřesňuje:

- [consolepi-session](../../usr/local/sbin/consolepi-session) pro **output** i
  **full** používá `picocom --logfile`. Vstup operátora nezapisuje samostatně.
- Aktivní cesta relace nevolá
  [consolepi-transcript-writer](../../usr/local/sbin/consolepi-transcript-writer),
  který obsahuje redakční logiku. Označení output jako „aktivní redakce“ tedy
  není zárukou redakce skutečně pořizovaného záznamu.
- Výstup zařízení může obsahovat zpětně vypsané příkazy, hesla či konfiguraci.
  Pro provoz bez ukládání terminálového obsahu ponechte **Pouze události**.
- Skutečný obsah logu na konkrétní instalaci je třeba ověřit řízeným testem
  s neškodnými testovacími údaji. Tato kontrola zdrojů neuzavírá akceptační testy.

Nápověda v hlavní větvi byla upřesněna. Vydaný image a instalační archiv 1.9.1
zůstávají původní a mohou stále zobrazovat starší popisky. Změna dokumentace
nepřidává recorder ani redakci do běžícího zařízení.

## Související dokumentace

[Obrazový přehled rozhraní](../WEB-UI.md), [instalace image](../INSTALACE-IMAGE-RPI-IMAGER.txt),
[čistá instalace](../INSTALACE-RPI3.md), [security policy](../../SECURITY.md)
a [vydání 1.9.1](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/tag/v1.9.1).
