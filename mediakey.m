// OldPhoneDeck media-key helper.
// Posts a system media key (play/pause, next, previous) so macOS routes it to
// whatever is actually playing — browser video, Spotify, Music, etc. — exactly
// like the physical media keys / Touch Bar. Never launches an app.
//
// Build:  clang -framework Cocoa -o mediakey mediakey.m
// Usage:  ./mediakey play | next | prev
#import <Cocoa/Cocoa.h>
#import <IOKit/hidsystem/ev_keymap.h>
#import <string.h>

static void postKey(int key) {
    for (int down = 1; down >= 0; down--) {
        NSEvent *e = [NSEvent otherEventWithType:NSEventTypeSystemDefined
                                        location:NSZeroPoint
                                   modifierFlags:(down ? 0xA00 : 0xB00)
                                       timestamp:0
                                    windowNumber:0
                                         context:nil
                                         subtype:8
                                           data1:(key << 16) | ((down ? 0xA : 0xB) << 8)
                                           data2:-1];
        CGEventPost(kCGHIDEventTap, [e CGEvent]);
    }
}

int main(int argc, const char *argv[]) {
    NSApplicationLoad();  // give the CLI tool an app context so [NSEvent CGEvent] works
    fprintf(stderr, "accessibility_trusted=%d\n", AXIsProcessTrusted());
    int key = NX_KEYTYPE_PLAY;
    if (argc > 1) {
        if (strcmp(argv[1], "next") == 0) key = NX_KEYTYPE_NEXT;
        else if (strcmp(argv[1], "prev") == 0) key = NX_KEYTYPE_PREVIOUS;
    }
    postKey(key);
    return 0;
}
