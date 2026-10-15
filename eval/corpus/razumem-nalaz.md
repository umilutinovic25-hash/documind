# Razumem nalaz

Instalabilna web-aplikacija (PWA) koja **slikaš laboratorijski nalaz** i dobiješ objašnjenje svakog parametra na srpskom — šta znači, da li je van referentnog opsega i koja pitanja da postaviš lekaru.

**Sve radi lokalno u pretraživaču.** Čitanje slike (OCR) i tumačenje se izvršavaju na uređaju — nijedna slika ni podatak ne odlazi na server.

## Kako se koristi

1. Otvori aplikaciju u pretraživaču (na telefonu).
2. „Slikaj nalaz" (kamera) ili „Izaberi sliku" (galerija) — aplikacija pročita tekst.
3. Proveri/ispravi očitani tekst i klikni **Objasni nalaz**.
4. Za svaki parametar vidiš status (u opsegu / blago van / izrazito van), gde vrednost pada u opsegu, i objašnjenje. Na dnu su predložena pitanja za lekara.

Bez slike možeš i ručno da nalepiš/ukucaš vrednosti.

## Instalacija na telefon (kao aplikacija)

Otvori sajt u Chrome-u (Android) ili Safari-ju (iPhone) → meni → **„Dodaj na početni ekran"**. Dobiješ ikonicu i radi kao aplikacija, i offline.

## Tehnički

- Čist HTML/CSS/JS, bez build koraka.
- OCR: [Tesseract.js](https://github.com/naptha/tesseract.js) (učitava se pri prvom korišćenju, potom keširan za offline).
- PWA: `manifest.webmanifest` + `sw.js` (service worker, stale-while-revalidate keš).
- Ikonice se generišu skriptom `node gen-icons.js` (bez spoljnih biblioteka).

## Napomena

Edukativna alatka, **nije zamena za lekara**. Referentni opsezi variraju od laboratorije do laboratorije i zavise od pola, uzrasta i konteksta.
