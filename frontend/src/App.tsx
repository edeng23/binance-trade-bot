import React from 'react';
import NavScreen from "./NavScreen";
import styled from "styled-components";
import {ThemeVariables} from "./ThemeVariables";
import MyCoinList from "./CoinListPage/MyCoinList";
import {BrowserRouter as Router, Route} from 'react-router-dom';
import HomePage from "./HomePage/HomePage";

function App() {
    return (
        <Router>
            <BodyWrapper>
                <NavScreen/>
                <Route path={'/'} exact>
                    <HomePage/>
                </Route>
                <Route path={'/coins'}>
                    <MyCoinList/>
                </Route>
            </BodyWrapper>
        </Router>
    );
}

export default App;

const BodyWrapper = styled.div`
   background-color: ${ThemeVariables.BackgroundColor};
   min-height: 100vh;
   min-width: 100vw;
    color: white;
   display: flex;
   flex-direction: column;
`;
