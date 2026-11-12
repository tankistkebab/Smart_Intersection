/*
 * ============================================================
 * CONTROLER INTERSECȚIE INTELIGENTĂ CU PRIORITATE AMBULANȚĂ
 * ============================================================
 * Autor   : Junie
 * Versiune: 1.2 (Senzori Non-Blocanti + Corectii Logica)
 * Descriere:
 * Sistem hibrid Arduino + Python pentru gestionarea unei
 * intersecții cu 4 direcții. Suportă mod standard de
 * semaforizare și mod de prioritate pentru ambulanță,
 * declanșat prin semnal Serial de la scriptul Python (CV).
 * ============================================================
 */

#include <Servo.h>

// ─── CONFIGURARE PINI SEMAFOARE ──────────────────────────────
// Ordinea: [Verde, Galben, Roșu]
const int TL_PINS[4][3] = {
  {50,  49,  48},   // TL1 - NORD: Verde Galben Rosu
  {37,  31,  39},   // TL2 - SUD
  {47,  41,  40},   // TL3 - EST
  {35,  34,  36}    // TL4 - VEST
};

// ─── CONFIGURARE PINI SENZORI ULTRASONICI ───────────────────
const int US_TRIG[4] = {23, 25, 44, 28}; // Trig: NORD, SUD, EST, VEST
const int US_ECHO[4] = {22, 24, 45, 26}; // Echo: NORD, SUD, EST, VEST

// ─── CONFIGURARE PINI SERVOMOTOARE ──────────────────────────
const int SV_PINS[4] = {3, 5, 9, 6}; // NORD, SUD, EST, VEST
Servo barriers[4];

// ─── CONSTANTE TIMING ────────────────────────────────────────
const int GREEN_DURATION   = 5000; // ms - durata Verde în mod standard
const int YELLOW_DURATION  = 2000; // ms - durata Galben
const int RED_MIN_DURATION = 1000; // ms - pauză minimă după trecere la Roșu
const int BARRIER_DELAY    =  200; // ms - întârziere între coborâri de bariere
const int AMBULANCE_GREEN  = 8000; // ms - Verde prioritar pentru ambulanță

// ─── CONSTANTE SERVO & SENZOR ────────────────────────────────
const int SERVO_UP        =  90; // grade - barieră ridicată
const int SERVO_DOWN      = 0;   // grade - barieră coborâtă
const float SAFE_DISTANCE =  7.0; // cm - distanță minimă pentru coborâre barieră

// ─── INDEXURI CULORI SEMAFOR ─────────────────────────────────
#define GREEN  0
#define YELLOW 1
#define RED    2

// ─── STARE SISTEM ────────────────────────────────────────────
int  currentGreen    = 0;    // Direcția curentă cu Verde (0-3)
bool ambulanceMode   = false;
int  ambulanceDir    = -1;   // Direcția ambulanței (-1 = niciuna)

// ============================================================
//  SETUP
// ============================================================
void setup() {
  Serial.begin(9600);
  Serial.println(F("[SISTEM] Intersectie Inteligenta v1.1 - Init..."));

  // Inițializează pinii semafoare ca OUTPUT
  for (int i = 0; i < 4; i++) {
    for (int c = 0; c < 3; c++) {
      pinMode(TL_PINS[i][c], OUTPUT);
      digitalWrite(TL_PINS[i][c], LOW);
    }
  }

  // Inițializează pinii senzori ultrasonici
  for (int i = 0; i < 4; i++) {
    pinMode(US_TRIG[i], OUTPUT);
    pinMode(US_ECHO[i], INPUT);
  }

  // Atașează și inițializează servomotoarele (bariere ridicate)
  for (int i = 0; i < 4; i++) {
    barriers[i].attach(SV_PINS[i]);
    barriers[i].write(SERVO_UP);
    delay(100);
  }

  // Pornire cu NORD Verde
  setTrafficLight(0, GREEN);
  setTrafficLight(1, RED);
  setTrafficLight(2, RED);
  setTrafficLight(3, RED);

  Serial.println(F("[SISTEM] Initializare completa. Ciclu standard pornit."));
}

// ============================================================
//  LOOP PRINCIPAL
// ============================================================
void loop() {
  checkSerialInput();

  if (ambulanceMode) {
    handleAmbulanceMode();
  } else {
    handleStandardCycle();
  }
}

// ============================================================
//  CITIRE SEMNAL SERIAL (de la Python CV)
// ============================================================
void checkSerialInput() {
  if (Serial.available() > 0) {
    char received = Serial.read();

    if (received >= '1' && received <= '4') {
      ambulanceDir  = received - '1';
      ambulanceMode = true;

      Serial.print(F("[AMBULANTA] Semnal primit! Directie: "));
      Serial.println(ambulanceDir);
    }
    else if (received == '0') {
      ambulanceMode = false;
      ambulanceDir  = -1;
      Serial.println(F("[SISTEM] Mod ambulanta dezactivat manual."));
    }
  }
}

// ============================================================
//  MOD STANDARD: Ciclu Verde → Galben → Roșu
// ============================================================
void handleStandardCycle() {
  Serial.print(F("[STANDARD] Verde pe directia "));
  Serial.println(currentGreen);

  setTrafficLight(currentGreen, GREEN);
  raiseBarrier(currentGreen);

  waitWithSerialCheck(GREEN_DURATION);
  if (ambulanceMode) return;

  setTrafficLight(currentGreen, YELLOW);
  waitWithSerialCheck(YELLOW_DURATION);
  if (ambulanceMode) return;

  // Pas intermediar: Toate semafoarele pe ROSU (faza de siguranta)
  for (int i = 0; i < 4; i++) {
    setTrafficLight(i, RED);
  }
  waitWithSerialCheck(RED_MIN_DURATION);
  if (ambulanceMode) return;

  currentGreen = (currentGreen + 1) % 4;

  for (int i = 0; i < 4; i++) {
    if (i == currentGreen) setTrafficLight(i, GREEN);
    else                   setTrafficLight(i, RED);
  }
}

// ============================================================
//  MOD AMBULANȚĂ: Prioritate imediată + Bariere Non-Blocante
// ============================================================
void handleAmbulanceMode() {
  Serial.print(F("[AMBULANTA] Prioritate activata pentru directia "));
  Serial.println(ambulanceDir);

  // Pasul 1: Toate semafoarele pe Galben
  for (int i = 0; i < 4; i++) {
    setTrafficLight(i, YELLOW);
  }
  delay(1000);

  // Pasul 2: Direcția ambulanței → Verde; celelalte → Roșu
  for (int i = 0; i < 4; i++) {
    if (i == ambulanceDir) setTrafficLight(i, GREEN);
    else                   setTrafficLight(i, RED);
  }

  // Pasul 3: Ridică bariera pe direcția ambulanței (dacă era coborâtă)
  raiseBarrier(ambulanceDir);

  // Pasul 4 & 5: Verificare independentă pentru coborârea celorlalte bariere
  Serial.println(F("[BARIERE] Initiere coborare independenta..."));
  
  // Array pentru a urmări ce bariere mai trebuie coborâte
  bool barrierNeedsToClose[4];
  for (int i = 0; i < 4; i++) {
    if (i != ambulanceDir) {
      barrierNeedsToClose[i] = true; 
    } else {
      barrierNeedsToClose[i] = false; // Bariera ambulanței rămâne sus
    }
  }

  unsigned long startAmbulance = millis();
  
  // În loc de delay() pasiv, monitorizăm senzorii pe durata priorității
  while (millis() - startAmbulance < (unsigned long)AMBULANCE_GREEN) {
    checkSerialInput(); // Citim serialul si in timpul modului ambulanta pentru a nu acumula comenzi
    
    for (int i = 0; i < 4; i++) {
      if (barrierNeedsToClose[i]) {
        float dist = getDistance(i);
        
        // Dacă e sigur, coboară acea barieră specifică
        if (dist >= SAFE_DISTANCE) {
          barriers[i].write(SERVO_DOWN);
          barrierNeedsToClose[i] = false; // Marcăm ca fiind coborâtă
          
          Serial.print(F("[BARIERA] Coborata pe directia "));
          Serial.println(i);
          delay(150); // Scurtă pauză pentru stabilitatea sursei de curent a servo-ului
        }
      }
    }
    delay(50); // Pauză mică pentru a nu bloca procesorul și senzorii
  }

  // Pasul 6: Revenire la modul standard
  ambulanceMode = false;
  currentGreen  = ambulanceDir;
  ambulanceDir  = -1;

  Serial.println(F("[SISTEM] Revenire la ciclu standard. Ridicare bariere..."));
  for (int i = 0; i < 4; i++) {
    raiseBarrier(i);
    delay(BARRIER_DELAY);
  }
}

// ============================================================
//  SETARE SEMAFOR
// ============================================================
void setTrafficLight(int dir, int color) {
  for (int c = 0; c < 3; c++) {
    digitalWrite(TL_PINS[dir][c], (c == color) ? HIGH : LOW);
  }
}

// ============================================================
//  RIDICARE BARIERĂ
// ============================================================
void raiseBarrier(int dir) {
  barriers[dir].write(SERVO_UP);
  delay(150); 
}

// ============================================================
//  MĂSURARE DISTANȚĂ HC-SR04
// ============================================================
float getDistance(int dir) {
  digitalWrite(US_TRIG[dir], LOW);
  delayMicroseconds(2);
  digitalWrite(US_TRIG[dir], HIGH);
  delayMicroseconds(10);
  digitalWrite(US_TRIG[dir], LOW);

  long duration = pulseIn(US_ECHO[dir], HIGH, 30000); 
  // Daca duration == 0 (timeout/deconectat), returnam 0.0 (pericol) in loc de 999.0
  float distance = (duration <= 0) ? 0.0 : (duration * 0.0343) / 2.0;

  return distance;
}

// ============================================================
//  AȘTEPTARE CU MONITORIZARE SERIAL
// ============================================================
void waitWithSerialCheck(int ms) {
  unsigned long start = millis();
  while (millis() - start < (unsigned long)ms) {
    checkSerialInput();
    if (ambulanceMode) return; 
    delay(50); 
  }
}