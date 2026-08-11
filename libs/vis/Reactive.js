let activeEffect = null;
const targetMap = new WeakMap();

function isObject(val) {
	return val !== null && typeof val === 'object';
}

function track(target, key) {
	if (!activeEffect) return;

	let depsMap = targetMap.get(target);
	if (!depsMap) {
		depsMap = new Map();
		targetMap.set(target, depsMap);
	}

	let dep = depsMap.get(key);
	if (!dep) {
		dep = new Set();
		depsMap.set(key, dep);
	}

	dep.add(activeEffect);
}

function trigger(target, key) {
	const depsMap = targetMap.get(target);
	if (!depsMap) return;

	const dep = depsMap.get(key);
	if (dep) {
		for (const effect of dep) {
			effect();
		}
	}
}

function createPrimitiveRef(initialValue) {
	let value = initialValue;

	const ref = {
		get value() {
			track(ref, 'value');
			return value;
		},
		set value(newVal) {
			if (value !== newVal) {
				value = newVal;
				trigger(ref, 'value');
			}
		},
		__isReactive: true
	};

	return ref;
}

function createReactiveObject(obj) {
	return new Proxy(obj, {
		get(target, key, receiver) {
			const result = Reflect.get(target, key, receiver);
			track(target, key);
			return isObject(result) ? reactive(result) : result;
		},
		set(target, key, value, receiver) {
			const old = target[key];
			const result = Reflect.set(target, key, value, receiver);
			if (old !== value) {
				trigger(target, key);
			}
			return result;
		}
	});
}

export function reactive(value) {
	return isObject(value) ? createReactiveObject(value) : createPrimitiveRef(value);
}

// NEW: Auto-tracking computed
export function computed(getter) {
	const result = reactive();
	const runner = () => {
		result.value = getter();
	};
	const refs = extractRefsFromGetter(getter); // or manually list them
	refs.forEach(ref => watch(ref, runner));
	runner();
	return result;
}

// Watch a reactive value or object's key
export function watch(refOrObj, callback, key) {
	const run = () => {
		const val = key ? refOrObj[key] : refOrObj.value ?? refOrObj;
		callback(val);
	};
	return effect(run);
}

// Core effect runner
export function effect(fn) {
	const runEffect = () => {
		try {
			activeEffect = runEffect;
			fn();
		} finally {
			activeEffect = null;
		}
	};

	runEffect._stop = () => {
		// For now, no dependency cleanup. Could be enhanced with dep tracking sets.
	};

	runEffect();
	return runEffect;
}
