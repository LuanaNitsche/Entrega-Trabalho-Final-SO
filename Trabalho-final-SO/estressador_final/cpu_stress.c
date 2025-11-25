#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

static volatile LONG g_stop_flag = 0;
BOOL WINAPI ConsoleCtrlHandler(DWORD ctrl_type)
{
    switch (ctrl_type) {
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
    case CTRL_CLOSE_EVENT:
    case CTRL_SHUTDOWN_EVENT:
        InterlockedExchange(&g_stop_flag, 1);
        return TRUE;
    default:
        return FALSE;
    }
}

DWORD WINAPI worker_thread(LPVOID lpParam)
{
    int cpu_index = (int)(intptr_t)lpParam;

    HANDLE hThread = GetCurrentThread();
    DWORD_PTR mask = ((DWORD_PTR)1) << cpu_index;
    DWORD_PTR old_mask = SetThreadAffinityMask(hThread, mask);
    if (old_mask == 0) {
        DWORD err = GetLastError();
        fprintf(stderr, "[Thread %d] Erro em SetThreadAffinityMask (%lu)\n",
                cpu_index, (unsigned long)err);
    }

    volatile double x = 1.23456789;

    for (;;) {
        if (g_stop_flag)
            break;

        for (int i = 0; i < 100000; i++) {
            x = x * 1.0000001 + 0.0000001;
            x = x / 1.00000007 + 0.00000009;
            x = x * x + 1.0;
        }

        _ReadWriteBarrier();
    }

    return 0;
}

int main(int argc, char* argv[])
{
    if (argc < 2) {
        fprintf(stderr, "Uso: %s <duracao_em_segundos> [num_threads]\n", argv[0]);
        return EXIT_FAILURE;
    }

    int duration = atoi(argv[1]);
    if (duration <= 0) {
        fprintf(stderr, "Duracao invalida\n");
        return EXIT_FAILURE;
    }

    SYSTEM_INFO si;
    GetSystemInfo(&si);
    int num_cpus = (int)si.dwNumberOfProcessors;
    if (num_cpus < 1) num_cpus = 1;

    int num_threads = (argc >= 3) ? atoi(argv[2]) : num_cpus;
    if (num_threads <= 0) num_threads = 1;
    if (num_threads > num_cpus) num_threads = num_cpus;

    printf("Estressando CPU por %d segundos usando %d threads (de %d CPUs logicos)\n",
           duration, num_threads, num_cpus);

    if (!SetConsoleCtrlHandler(ConsoleCtrlHandler, TRUE)) {
        fprintf(stderr, "Aviso: nao foi possivel registrar ConsoleCtrlHandler.\n");
    }

    // SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS);

    HANDLE* threads = (HANDLE*)calloc(num_threads, sizeof(HANDLE));
    if (!threads) {
        fprintf(stderr, "Erro de memoria\n");
        return EXIT_FAILURE;
    }

    for (int i = 0; i < num_threads; i++) {
        threads[i] = CreateThread(
            NULL,              
            0,                
            worker_thread,    
            (LPVOID)(intptr_t)i, 
            0,                 
            NULL              
        );
        if (!threads[i]) {
            DWORD err = GetLastError();
            fprintf(stderr, "Erro ao criar thread %d (erro %lu)\n",
                    i, (unsigned long)err);
        }
    }

    Sleep((DWORD)duration * 1000);

    InterlockedExchange(&g_stop_flag, 1);

    WaitForMultipleObjects(num_threads, threads, TRUE, INFINITE);

    for (int i = 0; i < num_threads; i++) {
        if (threads[i]) {
            CloseHandle(threads[i]);
        }
    }
    free(threads);

    printf("Finalizado.\n");
    return EXIT_SUCCESS;
}
