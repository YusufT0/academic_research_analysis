// MongoDB initialization script
// Bu script container ilk başlatıldığında çalışır
// NOT: Index'ler Beanie tarafından otomatik oluşturuluyor

// academic_research database'ini seç
db = db.getSiblingDB('academic_research');

// Collections oluştur (Beanie tarafından da oluşturulabilir ama 
// burada önceden oluşturmak performans için iyi)
db.createCollection('journals');
db.createCollection('issues');
db.createCollection('articles');

print('✅ MongoDB initialization completed!');
print('📊 Collections created: journals, issues, articles');
print('🔑 Indexes will be created by Beanie ODM');
