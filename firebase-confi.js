import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCz7SzF7PByWjUmc5c2BLOSvZnSBIytbF8",
  authDomain: "she360-35318.firebaseapp.com",
  projectId: "she360-35318",
  storageBucket: "she360-35318.firebasestorage.app",
  messagingSenderId: "208045991095",
  appId: "1:208045991095:web:83f4d65669b587d4cdd932"
};

const app = initializeApp(firebaseConfig);

export const auth = getAuth(app);
export const db = getFirestore(app);