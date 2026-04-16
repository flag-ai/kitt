package engines

import "testing"

type stubEngine struct{ name string }

func (s stubEngine) Spec() *Spec { return &Spec{Name: s.name} }

func TestRegistry_RegisterAndGet(t *testing.T) {
	r := NewRegistry()
	r.Register(stubEngine{name: "alpha"})
	r.Register(stubEngine{name: "beta"})

	if _, ok := r.Get("alpha"); !ok {
		t.Error("alpha missing")
	}
	if _, ok := r.Get("zeta"); ok {
		t.Error("unexpected zeta")
	}

	list := r.List()
	if len(list) != 2 || list[0].Name != "alpha" || list[1].Name != "beta" {
		t.Errorf("list sorted = %#v", list)
	}
}

func TestRegistry_DuplicateRegisterPanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic")
		}
	}()
	r := NewRegistry()
	r.Register(stubEngine{name: "dup"})
	r.Register(stubEngine{name: "dup"})
}

func TestRegistry_NilEnginePanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic")
		}
	}()
	r := NewRegistry()
	r.Register(nil)
}
