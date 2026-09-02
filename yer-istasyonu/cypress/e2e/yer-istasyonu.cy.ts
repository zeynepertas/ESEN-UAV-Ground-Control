// 'describe' bloğu, testlerimizin ana klasörüdür (Test Süiti). 
// İçerisine yazdığımız tüm testler "Yer İstasyonu Arayüz ve Buton Testleri" başlığı altında gruplanır.
describe('Yer İstasyonu Arayüz ve Buton Testleri', () => {
  
  // 'beforeEach', adından da anlaşılacağı gibi İÇERİDEKİ HER TESTTEN ('it' bloklarından) ÖNCE otomatik olarak 1 kez çalıştırılır.
  // Amacı: Her teste temiz bir sayfada başlamaktır.
  beforeEach(() => {
    // cy.visit(): Cypress'e (Sanal robota) Google Chrome'da hangi web sitesine/URL'ye gideceğini söyler.
    // Bizim Angular projemiz yerelde 4200 portunda çalıştığı için oraya gidiyoruz.
    cy.visit('http://localhost:4200');
  });

  // 'it' bloğu, tek bir test senaryosunu (Test Case) temsil eder (İngilizcedeki "it should..." kalıbından gelir).
  it('1. Uygulama başarılı şekilde açılmalı ve başlık görünmeli', () => {
    // cy.contains('Metin'): Sayfanın HTML kodları içinde dolaşır ve yazdığımız metni (ESEN YER KONTROL İSTASYONU) arar.
    // .should('be.visible'): Bulduğu bu metnin sayfada GERÇEKTEN GÖRÜNÜR olup olmadığını (CSS ile gizlenip gizlenmediğini) doğrular.
    // Eğer başlık sayfada görünmüyorsa test burada "HATA" (Failed) verir ve süreci durdurur.
    cy.contains('ESEN YER KONTROL İSTASYONU').should('be.visible');
  });

  it('2. Otonom Görev Kontrol butonlarına tıklanabilmeli', () => {
    // cy.contains('button', 'Metin'): Sayfadaki HTML etiketlerinden sadece <button> olanları bulur ve içinde 'Eve Dönüş (RTL)' yazan butonu seçer.
    // .click(): Cypress'in seçtiği o butonun üzerine faresini götürüp fiziksel bir sol tık yapmasını sağlar.
    cy.contains('button', 'Eve Dönüş (RTL)').click();
    cy.contains('button', 'Dikey İniş (LAND)').click();
    cy.contains('button', 'Acil Motor Durdurma').click();
  });

  it('3. Manuel Uçuş ve Joystick butonlarına tıklanabilmeli', () => {
    // Önce standart bir butona tıklıyoruz.
    cy.contains('button', 'Otomatik Kalkış / Devriye').click();
    
    // Joystick butonlarında isim (Kuzey, Güney yazısı) butonun içinde değil, HTML'in 'title' özelliğinin içindeydi (Fareyle üzerine gelince çıkan yazı).
    // cy.get(): CSS seçicileri (Selectors) kullanarak HTML'de nokta atışı arama yapar.
    // cy.get('button[title="Kuzey"]') demek -> "Lütfen bana title özelliği 'Kuzey' olan butonu bul ve getir" demektir.
    cy.get('button[title="Kuzey"]').click();
    cy.get('button[title="Batı"]').click();
    cy.get('button[title="Güney"]').click();
    cy.get('button[title="Doğu"]').click();
  });

  it('4. Karakutu tablosu yüklenmeli ve Rapor butonu çalışmalı', () => {
    // Karakutu tablosunun arayüzde görünür olduğunu (Sorunsuz yüklenip yüklenmediğini) doğrular
    cy.contains('UÇUŞ VERİ KAYITLARI (KARAKUTU)').should('be.visible');
    
    // Ardından o bölümdeki rapor indirme butonuna basarak dosya indirme fonksiyonunun (CSV) tetiklendiğini test eder.
    cy.contains('button', 'RAPOR İNDİR (CSV)').click();
  });
  
    it('5. Veritabanı Filtreleme çalışmalı ve veriyi doğrulamalı', () => {
    // 1. Arayüzdeki dropdown menüsünü bul ve içinden 'alarmlar' seçeneğini otomatik seç
    cy.get('select').select('alarmlar');
    
    // 2. Python'un veritabanına bağlanıp sadece alarmları getirmesi için 1 saniye bekle
    cy.wait(1000);
    
    // 3. DOĞRULAMA (DATA VALIDATION): Tabloda artık 'NORMAL' yazısı OLMAMALI! 
    // Cypress tüm tabloyu okur ve 'NORMAL' kelimesini bulamazsa testi başarıyla geçer.
    cy.get('.history-panel').should('not.contain', 'NORMAL');
  });
});