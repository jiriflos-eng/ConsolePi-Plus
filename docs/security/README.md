# ConsolePi+ 1.9.1 – podklady pro bezpečnostní posouzení

Aktualizováno 6. 10. 2026. Dokumenty popisují vydání 1.9.1 a obsahují skutečné
výřezy z webu testovacího Raspberry Pi 3 B+. Ukazují příklad nastavení zařízení
192.168.100.124; nejde o doporučenou adresu ani důkaz vynucení bezpečnostních pravidel.

- [Bezpečnostní přehled pro auditora (DOCX)](01_Bezpecnostni_prehled_pro_auditora_se_screenshoty.docx)
- [Technická bezpečnostní dokumentace (DOCX)](02_Technicka_bezpecnostni_dokumentace_se_screenshoty.docx)
- [Akceptační testy a obrazové reference (XLSX)](03_Akceptacni_testy_se_screenshoty.xlsx)

Obrázky S01–S16 jsou propojené s listem **Reference** v sešitu. Všech deset
testů je nadále **Nevyhodnoceno**; původní vzorce a výběr výsledků jsou zachované.
Screenshoty neověřují například nftables, oprávnění souborů, TLS protokoly,
zamítnutí podvrženého balíčku ani přístup z nepovolené sítě. Při pořízení nebyla
spuštěna obnova, záloha, změna hesla nebo instalace aktualizací.

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
