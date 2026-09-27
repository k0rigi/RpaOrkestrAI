"""Offline Playwright integration check: no credentials and no external websites."""

from rpa_orkestrai.integrations.browser import BrowserService


def main() -> None:
    with BrowserService() as browser:
        browser.page.set_content("""
            <!doctype html><html lang="tr"><meta charset="utf-8">
            <label for="name">Departman</label><input id="name">
            <button id="run" onclick="document.querySelector('#result').textContent =
                document.querySelector('#name').value + ' hazır'">Hazırla</button>
            <p id="result"></p></html>
        """)
        browser.fill("#name", "Finans")
        browser.click("#run")
        browser.wait_for("#result")
        assert browser.text("#result") == "Finans hazır"
    print("Playwright: alan doldurma, tıklama, metin okuma ve kaynak kapatma başarılı.")


if __name__ == "__main__":
    main()
