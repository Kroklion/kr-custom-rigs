import traceback
from rigify.generate import Generator

# Save original function
_original_generate = Generator.generate

# Callback registries
pre_generate_callbacks = []
post_generate_callbacks = []


# -----------------------------
#   Callback registration API
# -----------------------------

def add_pre_generate_callback(func):
    if func not in pre_generate_callbacks:
        pre_generate_callbacks.append(func)


def remove_pre_generate_callback(func):
    if func in pre_generate_callbacks:
        pre_generate_callbacks.remove(func)


def add_post_generate_callback(func):
    if func not in post_generate_callbacks:
        post_generate_callbacks.append(func)


def remove_post_generate_callback(func):
    if func in post_generate_callbacks:
        post_generate_callbacks.remove(func)


# -----------------------------
#   Hooked generate function
# -----------------------------

def hook_generate(self):
    # Run pre-callbacks
    for cb in pre_generate_callbacks:
        try:
            cb(self)
        except Exception as e:
            print(f"[gen_hooks] Pre-callback error: {e}")
            traceback.print_exc()

    # Call original generate
    result = _original_generate(self)

    # Run post-callbacks
    for cb in post_generate_callbacks:
        try:
            cb(self)
        except Exception as e:
            print(f"[gen_hooks] Post-callback error: {e}")
            traceback.print_exc()

    return result


# -----------------------------
#   Registration
# -----------------------------

def register():
    Generator.generate = hook_generate


