// Experimental Xbox interface rumble bridge for the Vader 5 Pro dongle.
#define _GNU_SOURCE
#include <errno.h>
#include <libusb-1.0/libusb.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;
static void stop_running(int signo) { (void)signo; running = 0; }

int main(void) {
    int sock = socket(AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC, 0);
    if (sock < 0) { perror("socket"); return 1; }
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    int name_length = snprintf(addr.sun_path + 1, sizeof(addr.sun_path) - 1,
                               "vader5-rumble-%lu", (unsigned long)getuid());
    if (name_length < 0 || name_length >= (int)sizeof(addr.sun_path) - 1) { close(sock); return 1; }
    socklen_t addr_length = offsetof(struct sockaddr_un, sun_path) + 1 + name_length;
    int passcred = 1;
    if (setsockopt(sock, SOL_SOCKET, SO_PASSCRED, &passcred, sizeof(passcred)) < 0 ||
        bind(sock, (struct sockaddr *)&addr, addr_length) < 0) { perror("bind"); close(sock); return 1; }
    signal(SIGINT, stop_running);
    signal(SIGTERM, stop_running);

    libusb_context *usb = NULL;
    if (libusb_init(&usb) != 0) { close(sock); return 1; }
    libusb_device_handle *pad = NULL;
    while (running) {
        uint8_t motors[2];
        struct pollfd pfd = {.fd = sock, .events = POLLIN};
        int polled = poll(&pfd, 1, 500);
        if (polled <= 0) continue;
        struct iovec iov = {.iov_base = motors, .iov_len = sizeof(motors)};
        union { struct cmsghdr align; char bytes[CMSG_SPACE(sizeof(struct ucred))]; } control;
        struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
                             .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
        if (recvmsg(sock, &msg, 0) != sizeof(motors) || (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) continue;
        bool authorized = false;
        for (struct cmsghdr *cmsg = CMSG_FIRSTHDR(&msg); cmsg; cmsg = CMSG_NXTHDR(&msg, cmsg)) {
            if (cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_CREDENTIALS &&
                cmsg->cmsg_len >= CMSG_LEN(sizeof(struct ucred))) {
                struct ucred *cred = (struct ucred *)CMSG_DATA(cmsg);
                authorized = cred->uid == getuid();
            }
        }
        if (!authorized) continue;
        if (!pad) {
            pad = libusb_open_device_with_vid_pid(usb, 0x37d7, 0x2401);
            if (!pad) { fprintf(stderr, "Vader 5 Pro USB dongle unavailable\n"); continue; }
            int rc = libusb_claim_interface(pad, 0);
            if (rc != 0) {
                fprintf(stderr, "Interface 0 unavailable: %s (is xpad bound?)\n", libusb_error_name(rc));
                libusb_close(pad); pad = NULL; continue;
            }
        }
        uint8_t packet[8] = {0x00, 0x08, 0x00, motors[0], motors[1], 0, 0, 0};
        int transferred = 0;
        int rc = libusb_interrupt_transfer(pad, 0x05, packet, sizeof(packet), &transferred, 100);
        if (rc != 0 || transferred != sizeof(packet)) {
            fprintf(stderr, "Xbox rumble write failed: %s\n", libusb_error_name(rc));
            libusb_release_interface(pad, 0);
            libusb_close(pad); pad = NULL;
        }
    }
    if (pad) {
        uint8_t off[8] = {0, 8, 0, 0, 0, 0, 0, 0};
        int transferred = 0;
        libusb_interrupt_transfer(pad, 0x05, off, sizeof(off), &transferred, 100);
        libusb_release_interface(pad, 0);
        libusb_close(pad);
    }
    libusb_exit(usb);
    close(sock);
    return 0;
}
