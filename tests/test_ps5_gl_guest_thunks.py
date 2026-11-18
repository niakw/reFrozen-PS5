"""Unit tests for exact Win64 guest -> OpenGL thunk generation."""
from pathlib import Path
import tempfile
import unittest

from scripts.ps5.gen_gl_guest_thunks import (
    GenerationError,
    generate,
    parse_headers,
)


HEADER = r"""
typedef unsigned int GLenum;
typedef unsigned int GLbitfield;
typedef int GLint;
typedef int GLsizei;
typedef unsigned int GLuint;
typedef float GLfloat;
typedef double GLdouble;
typedef unsigned char GLubyte;
typedef long long GLint64;
typedef unsigned long long GLuint64;
typedef long long GLintptr;
typedef long long GLsizeiptr;
typedef void *GLsync;
typedef void (APIENTRYP GLDEBUGPROC)(GLenum, GLenum, GLuint, GLenum, GLsizei,
                                     const char *, const void *);

GLAPI void APIENTRY glClear(GLbitfield mask);
GLAPI void APIENTRY glClearColor(GLfloat r, GLfloat g, GLfloat b, GLfloat a);
GLAPI void APIENTRY glViewport(GLint x, GLint y, GLsizei w, GLsizei h);
GLAPI void APIENTRY glDepthRange(GLdouble nearValue, GLdouble farValue);
GLAPI void APIENTRY glBufferData(GLenum target, GLsizeiptr size,
                                 const void *data, GLenum usage);
GLAPI const GLubyte * APIENTRY glGetString(GLenum name);
GLAPI void * APIENTRY glMapBuffer(GLenum target, GLenum access);
GLAPI GLenum APIENTRY glGetError(void);
GLAPI GLuint64 APIENTRY glGetTextureHandleARB(GLuint texture);
GLAPI GLsync APIENTRY glFenceSync(GLenum condition, GLbitfield flags);
GLAPI void APIENTRY glMany(GLint a, GLint b, GLint c, GLint d, GLfloat e,
                           GLdouble f, const void *g);
GLAPI void APIENTRY glDebugMessageCallback(GLDEBUGPROC callback,
                                           const void *userParam);
"""


class GlThunkGeneratorTest(unittest.TestCase):
    def _prototypes(self):
        with tempfile.TemporaryDirectory() as temp:
            header = Path(temp) / "gl.h"
            header.write_text(HEADER, encoding="utf-8")
            return parse_headers([header])

    def test_win64_register_and_stack_abi(self):
        generated = generate(
            self._prototypes(),
            [
                "glClear", "glClearColor", "glDepthRange", "glBufferData",
                "glGetString", "glMapBuffer", "glGetError",
                "glGetTextureHandleARB", "glFenceSync", "glMany",
            ],
        )
        self.assertIn("glClear((GLbitfield)A0);", generated)
        self.assertIn("glClearColor(AF(0), AF(1), AF(2), AF(3));", generated)
        self.assertIn("glDepthRange(AD(0), AD(1));", generated)
        self.assertIn(
            "glBufferData((GLenum)A0, (GLsizeiptr)A1, "
            "(const void *)(uintptr_t)A2, (GLenum)A3);",
            generated,
        )
        self.assertIn("RET((uintptr_t)glGetString((GLenum)A0));", generated)
        self.assertIn("RET((uintptr_t)glMapBuffer((GLenum)A0, (GLenum)A1));", generated)
        self.assertIn("RET((uint32_t)glGetError());", generated)
        self.assertIn("RET((uint64_t)glGetTextureHandleARB((GLuint)A0));", generated)
        self.assertIn("RET((uintptr_t)glFenceSync(", generated)
        self.assertIn("rdf(c->rsp + 8 + 8 * 4)", generated)
        self.assertIn("rdd(c->rsp + 8 + 8 * 5)", generated)
        self.assertIn("(const void *)(uintptr_t)AN(6)", generated)
        self.assertIn(
            'return rt_host_fn(proc.function, proc.name);',
            generated,
        )

    def test_exact_allowlist_deduplicates_and_ignores_comments(self):
        generated = generate(self._prototypes(), ["glClear", "", "glClear", "# note"])
        self.assertEqual(generated.count("void I_opengl32_dll_glClear("), 1)
        self.assertNotIn("glClearColor", generated)

    def test_missing_function_fails_closed(self):
        with self.assertRaisesRegex(GenerationError, "not found"):
            generate(self._prototypes(), ["glDefinitelyNotReal"])

    def test_callback_argument_fails_closed(self):
        with self.assertRaisesRegex(GenerationError, "callback"):
            generate(self._prototypes(), ["glDebugMessageCallback"])


if __name__ == "__main__":
    unittest.main()
