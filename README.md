# StressLab — Estressador de CPU (GUI + C)
### Gabriel Cestari, Luana Nitsche, Thomas Haskel


Projeto de Sistemas Operacionais que estressa a **CPU** via:

- **GUI em Python/Tkinter** (controle de tempo, núcleos e monitoramento)
- **Binário em C para Windows** (`cpu_stress.exe`) usando **WinAPI**:
    - `CreateThread`, `SetThreadAffinityMask`, `WaitForMultipleObjects`, `Sleep`
    - Cada thread é fixada em um core lógico (afinidade)

> Importante: a GUI chama um executável local. Você precisa compilar cpu_stress.c para gerar cpu_stress.exe na mesma pasta da interface.
> 

---

## Estrutura do projeto

```
estressador_final/
├─ cpu_stress.c           # fonte C (WinAPI)
├─ cpu_stress.exe         # executável (gerado a partir do .c)
├─ stress_gui.py          # interface Tkinter (somente CPU)
├─ requirements.txt       # dependências Python (opcional)
└─ README.md

```

> O arquivo cpu_stress.exe não vem versionado por padrão — gere localmente a partir do cpu_stress.c.
> 

---

## Pré-requisitos

### Windows

- **Python 3.10+** (Tkinter já vem junto no instalador oficial)
- **Compilador C** (escolha **um**):
    - **MSVC (recomendado):** Visual Studio **com** a workload
        
        *“Desenvolvimento para desktop com C++”* (ou *Build Tools for VS*).
        
    - **MinGW-w64 (MSYS2):** `gcc` para gerar `.exe`.

### Python (libs)

- `psutil` (para uso/temperatura da CPU)
- (Tkinter já está no Python do Windows)

Instalação rápida das libs:

```bash
pip install psutil
# (ou) pip install -r requirements.txt

```

> Temperatura: alguns notebooks não expõem sensores via psutil.sensors_temperatures() no Windows. Se aparecer “N/D” é limitação do driver/sensor.
> 

---

## Como compilar o estressor de CPU (Windows)

### Opção A — **MSVC** (`cl.exe`) – Visual Studio

1. Abra o **Visual Studio Installer** e **marque** a carga
    
    **“Desenvolvimento para desktop com C++”**.
    
    (Se já tiver instalado, clique em **Modificar** e adicione essa workload.)
    
2. Abra o atalho **Developer Command Prompt for VS 2022**.
3. Vá até a pasta do projeto:
    
    ```bash
    cd C:\Users\<SEU_USUARIO>\...\estressador_final
    
    ```
    
4. Compile:
    
    ```bash
    cl cpu_stress.c /O2 /Fe:cpu_stress.exe
    
    ```
    
5. Deve aparecer `cpu_stress.exe` na pasta.

### Opção B — **MinGW-w64 / MSYS2** (`gcc`)

1. Instale **MSYS2**: [https://www.msys2.org/](https://www.msys2.org/)
2. Abra **MSYS2 MinGW 64-bit** e rode:
    
    ```bash
    pacman -S --needed mingw-w64-x86_64-gcc
    
    ```
    
3. Vá até a pasta do projeto:
    
    ```bash
    cd /c/Users/<SEU_USUARIO>/.../estressador_final
    
    ```
    
4. Compile:
    
    ```bash
    gcc cpu_stress.c -O2 -o cpu_stress.exe
    
    ```
    
5. Confirme que `cpu_stress.exe` foi gerado.

> Obs.: A GUI procura cpu_stress.exe na mesma pasta.
> 
> 
> Em Linux/WSL você pode compilar para `cpu_stress` (sem `.exe`) e rodar a GUI lá também, mas este projeto foi pensado para **Windows**.
> 

---

## Como executar a GUI

1. (Opcional) Crie e ative um ambiente virtual:
    
    ```bash
    python -m venv .venv
    .venv\Scripts\activate
    
    ```
    
2. Instale as dependências:
    
    ```bash
    pip install psutil
    
    ```
    
3. Certifique-se de que **`cpu_stress.exe` está na mesma pasta**.
4. Rode a interface:
    
    ```bash
    python stress_gui.py
    
    ```
    

### Uso da interface

- **Núcleos CPU a estressar:** número de threads (cada uma presa a um core lógico).
- **Tempo limite (s):** tempo total do teste.
- **Temperatura limite (°C):** se disponível, a GUI interrompe ao atingir esse valor.
- **Iniciar estresse / Parar:** controla o processo nativo.
- A barra de progresso e o painel mostram **uso de CPU** e **temperatura** (quando suportada).

---

## Como validar pelo terminal (opcional)

### PowerShell — acompanhar uso de CPU (PT-BR)

- **Por núcleo:**
    
    ```powershell
    Get-Counter '\Processador(*)\% tempo de processador' -SampleInterval 1 -Continuous
    
    ```
    
- **Total:**
    
    ```powershell
    Get-Counter '\Processador(_Total)\% tempo de processador' -SampleInterval 1 -Continuous
    
    ```
    

(Interrompa com **Ctrl+C**.)

### CMD (`typeperf`)

```bash
typeperf "\Processador(*)\% tempo de processador" -si 1

```

---

## Erros comuns & soluções

- **“Binário cpu_stress(.exe) não encontrado”**
    
    → Gere o executável (ver seção **Compilar**) e **deixe-o na mesma pasta** do `stress_gui.py`.
    
- **`'cl' não é reconhecido`**
    
    → Falta o compilador MSVC. Abra o **Visual Studio Installer** e instale a workload
    
    **“Desenvolvimento para desktop com C++”**. Reabra o **Developer Command Prompt**.
    
- **Temperatura aparece “N/D”**
    
    → O Windows/driver não expõe sensores de CPU via `psutil`. É esperado em alguns modelos.
    
- **GUI não inicia / Tkinter ausente**
    
    → Reinstale o Python **oficial** do Windows ([https://python.org](https://python.org/)) – o Tkinter já vem incluso.
    

---

## Detalhes técnicos (para o relatório)

- **Estrategia de estresse:** loop intensivo em ponto flutuante para ocupar ALU/FPU.
- **Controle por SO:**
    - **Afinidade por thread:** `SetThreadAffinityMask` fixa cada thread em um core lógico.
    - **Parada ordenada:** flag global + `WaitForMultipleObjects`.
    - **Sinais de console:** `SetConsoleCtrlHandler` captura Ctrl+C/fechamento.
    - **Prioridade:** `SetPriorityClass(HIGH_PRIORITY_CLASS)` (opcional).
- **Monitoramento na GUI:** `psutil.cpu_percent()` (+ sensores de temperatura quando presentes).
